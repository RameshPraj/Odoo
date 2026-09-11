# -*- coding: utf-8 -*-
r"""The Export fiscal position must zero-rate, and only the Export position (ACC-3).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np --stop-after-init

Written against the invoice, not the configuration, because the configuration was not
what was wrong: the position was applied to the invoice correctly and then substituted
nothing. A test asserting "the Export position exists and lists VAT 0%" would have
passed throughout the defect.
"""
from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestExportZeroRating(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        nepal = cls.env.ref("base.np")
        cls.company = cls.env["res.company"].create({
            "name": "Nepal Fiscal Position Test",
            "country_id": nepal.id,
        })
        cls.env["account.chart.template"].try_loading(
            "np", company=cls.company, install_demo=False,
        )
        cls.env = cls.env(context={
            **cls.env.context,
            "allowed_company_ids": [cls.company.id],
        })
        cls.vat13 = cls.env["account.tax"].search([
            ("company_id", "=", cls.company.id),
            ("amount", "=", 13.0), ("type_tax_use", "=", "sale"),
        ], limit=1)
        cls.export_fp = cls.env.ref(
            f"account.{cls.company.id}_fiscal_position_np_export",
            raise_if_not_found=False)
        # The tax has to arrive via the product, not via `tax_ids` at create. See
        # `_invoice`.
        cls.product = cls.env["product.product"].create({
            "name": "ACC-3 fixture",
            "taxes_id": [Command.set(cls.vat13.ids)],
        })

    def _invoice(self, partner, amount=1000.0):
        """One invoice line whose tax arrives from the product, as it does in the UI.

        Deliberately *not* `tax_ids` passed at create. `tax_ids` is computed, stored
        and writable, so a value supplied at create wins over `_compute_tax_ids` --
        and it is `_compute_tax_ids` that applies the fiscal position. Supplying the
        tax directly therefore pins the line to 13% and no position can ever map it.

        This is not hypothetical: the first version of this file did exactly that and
        reported "an export invoice is still taxed at 13%" against a database where
        the fix had already been verified working by hand. The test was wrong, not the
        fix. A test has to enter through the same door the user does.
        """
        return self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "invoice_date": "2026-08-01",
            "invoice_line_ids": [Command.create({
                "product_id": self.product.id,
                "quantity": 1,
                "price_unit": amount,
            })],
        })

    def _partner(self, name, position=None):
        return self.env["res.partner"].create({
            "name": name,
            "property_account_position_id": position and position.id or False,
        })

    # ------------------------------------------------------------------
    def test_an_export_invoice_carries_no_vat(self):
        """The defect itself: this produced VAT 13% and 130.00 of tax."""
        self.assertTrue(self.export_fp, "the Export fiscal position is missing")
        inv = self._invoice(self._partner("NP Export Customer", self.export_fp))

        self.assertEqual(inv.fiscal_position_id, self.export_fp,
                         "the position did not reach the invoice")
        rates = inv.invoice_line_ids.tax_ids.mapped("amount")
        self.assertNotIn(13.0, rates,
                         f"an export invoice is still taxed at 13%: {rates}")
        self.assertEqual(inv.amount_tax, 0.0)
        self.assertEqual(inv.amount_total, 1000.0)

    def test_a_domestic_invoice_still_carries_vat(self):
        """The other half, and the one that matters more.

        Zero-rating everything would satisfy the test above while understating output
        VAT — under-collecting tax, which is worse than the bug being fixed. This is
        the assertion that stops an over-broad 'fix'.
        """
        inv = self._invoice(self._partner("NP Domestic Customer"))

        self.assertFalse(inv.fiscal_position_id,
                         "fixture assumption: no position on this partner")
        self.assertEqual(inv.invoice_line_ids.tax_ids.mapped("amount"), [13.0])
        self.assertEqual(inv.amount_tax, 130.0)
        self.assertEqual(inv.amount_total, 1130.0)

    def test_the_replaces_link_is_maintainable_in_the_ui(self):
        """`is_domestic` on the 13% taxes -- a UI concern, not a runtime one.

        An earlier version of this test claimed substitution was gated on `is_domestic`
        at `account_tax.py:5160`. That was wrong: `:5160` is in a bill-import matching
        helper and its `is_domestic` is the one on `account.fiscal.position`. A negative
        control settled it -- clearing `domestic_fiscal_position_id` left an export
        invoice at 0%, while clearing `original_tax_ids` restored 13%.

        What it does gate is the `Replaces` field's own domain
        `[('is_domestic', '=', True)]` (`:110`) and the "Domestic" tax filter (`:262`).
        The migration writes the link by ORM, where domains are not enforced, so
        without this an accountant opening VAT 0% would find an empty dropdown and no
        way to maintain the link by hand. Asserted because a correct-but-uneditable
        configuration is its own kind of trap.
        """
        self.assertTrue(
            self.company.domestic_fiscal_position_id,
            "company.domestic_fiscal_position_id is unset, so no tax is is_domestic "
            "and the Replaces field offers nothing to select")
        for tax in self.env["account.tax"].search([
                ("company_id", "=", self.company.id), ("amount", "=", 13.0)]):
            with self.subTest(tax=tax.name, use=tax.type_tax_use):
                self.assertTrue(tax.is_domestic)

    def test_the_zero_rated_taxes_declare_what_they_replace(self):
        """Without `original_tax_ids` there is nothing for the position to swap.

        This is the load-bearing half of ACC-3, confirmed by negative control: clearing
        this link on an otherwise fixed database put an export invoice straight back to
        `[13.0]` / `tax=130.0`.
        """
        zero_rated = self.env["account.tax"].search([
            ("company_id", "=", self.company.id),
            ("amount", "=", 0.0),
            ("fiscal_position_ids", "in", self.export_fp.ids),
        ])
        self.assertTrue(zero_rated, "no zero-rated tax is attached to the Export position")
        for tax in zero_rated:
            with self.subTest(tax=tax.name, use=tax.type_tax_use):
                self.assertEqual(
                    tax.original_tax_ids.mapped("amount"), [13.0],
                    f"{tax.name} ({tax.type_tax_use}) does not declare the 13% tax it "
                    f"replaces, so the Export position will leave VAT on the line")
