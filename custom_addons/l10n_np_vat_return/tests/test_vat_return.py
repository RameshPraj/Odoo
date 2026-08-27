# -*- coding: utf-8 -*-
"""Tests for the Nepal VAT return framework.

These prove the mechanism, not any particular form layout -- none ships.
The important guarantees:

  * with no form defined, computing raises a clear error rather than a blank return
  * box amounts come from tax tags on posted journal items, so they tie to the ledger
  * forms are versioned: a return keeps the form that applied to its period
  * formula boxes only accept a tiny arithmetic grammar, never arbitrary Python
"""
import os

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@tagged("-at_install", "post_install")
class TestVatReturn(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Form = cls.env["l10n_np.vat.return.form"]
        cls.Return = cls.env["l10n_np.vat.return"]
        cls.partner = cls.env["res.partner"].create({"name": "VAT Customer"})
        cls.sale_tax = cls.env["account.tax"].search(
            [("company_id", "=", cls.company.id), ("type_tax_use", "=", "sale")],
            order="amount desc", limit=1)

    def _post_invoice(self, amount, date="2026-08-01"):
        inv = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_date": date,
            "invoice_line_ids": [Command.create({
                "name": "Taxable supply", "quantity": 1, "price_unit": amount,
                "tax_ids": [Command.set(self.sale_tax.ids)],
            })],
        })
        inv.action_post()
        return inv

    def _tags_of_sale_tax(self):
        """Tax tags actually attached to the sale tax's repartition lines."""
        return self.sale_tax.repartition_line_ids.mapped("tag_ids")

    # ------------------------------------------------------------------
    # `test_xml_is_well_formed` lived here, in four near-identical copies across
    # four modules, while twelve modules shipping XML had no such test at all
    # (**COD-2**). It moved to `tools/check_xml_wellformed.py`, which `lint` runs.
    #
    # The check needs no ORM, no database and no registry -- it is a filesystem
    # walk and an `lxml` parse -- so paying for a database and a module install to
    # run it was the wrong trade, and a test could only ever cover modules that
    # already had a `tests/` directory. The tool covers all 79 XML files across 16
    # modules, including those with no tests, in about a second.

    def test_ships_with_no_form(self):
        """The IRD defines the layout; shipping a guess would be worse than nothing.

        Asserted against **what this module owns**, not against the database being
        empty (**TST-2**). The previous version was
        `assertFalse(self.Form.search_count([]))`, which would begin failing
        permanently the day an accountant entered the real IRD layout — the single
        most important thing anyone will ever do with this module, and the event
        that unblocks the FIN-1 go-live gate. A test that fails on success gets
        deleted, taking its assertion with it.

        `ir.model.data` answers the question actually being asked: did this
        module's data files create a form? A form an accountant enters has no
        xmlid and is invisible here.
        """
        shipped = self.env["ir.model.data"].search_count([
            ("model", "=", "l10n_np.vat.return.form"),
            ("module", "=", "l10n_np_vat_return"),
        ])
        self.assertEqual(
            shipped, 0,
            "No VAT return form may ship with this module.",
        )

    def test_compute_without_form_raises(self):
        ret = self.Return.create({
            "name": "VAT test", "date_from": "2026-07-17", "date_to": "2026-08-31",
            "company_id": self.company.id,
        })
        with self.assertRaises(UserError) as ctx:
            ret.action_compute()
        self.assertIn("No VAT return form is configured", str(ctx.exception))

    def _tagged_sale_tax(self):
        """A 13% sale tax whose repartition lines carry tags, built here.

        The chart's own tax is deliberately not used. Doing so was how this test
        managed to skip: it read tags off whatever the chart happened to provide, and
        when the chart provided none, the test excused itself under exactly the
        condition it existed to detect (TST-1). A fixture cannot be absent.

        Whether the *chart* is wired is a separate question, asserted by
        test_chart_taxes_carry_repartition_tags below. That one is allowed to fail;
        this one is not.
        """
        Tag = self.env["account.account.tag"]
        base_tag, tax_tag = Tag.create([
            {"name": "TST Base", "applicability": "taxes"},
            {"name": "TST Tax", "applicability": "taxes"},
        ])
        tax = self.env["account.tax"].create({
            "name": "TST VAT 13%",
            "amount": 13.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "company_id": self.company.id,
            "repartition_line_ids": [
                Command.create({"document_type": "invoice", "repartition_type": "base",
                                "factor_percent": 100, "tag_ids": [Command.set(base_tag.ids)]}),
                Command.create({"document_type": "invoice", "repartition_type": "tax",
                                "factor_percent": 100, "tag_ids": [Command.set(tax_tag.ids)]}),
                Command.create({"document_type": "refund", "repartition_type": "base",
                                "factor_percent": 100, "tag_ids": [Command.set(base_tag.ids)]}),
                Command.create({"document_type": "refund", "repartition_type": "tax",
                                "factor_percent": 100, "tag_ids": [Command.set(tax_tag.ids)]}),
            ],
        })
        return tax, base_tag + tax_tag

    def test_chart_taxes_carry_repartition_tags(self):
        """The Nepali chart's own taxes must carry tax tags. Guards FIN-1.

        Without these, `_tag_balance` matches no journal item and every box computes
        zero, silently: `vat_return.py:143-144` returns 0.0 for an empty tag set with
        no warning. A filed return would report nil while sales existed.

        The template is correct (`l10n_np/data/template/account.tax-np.csv`); the
        risk is the live database drifting from it, because Odoo instantiates chart
        data when a company *adopts* the chart, not on `-u`.
        """
        if self.company.chart_template != "np":
            # DELIBERATE SKIP — see the equivalent note in
            # l10n_np/tests/test_fiscal_positions.py. This asserts a property of
            # the shipped NP chart's taxes; off that chart there is nothing to
            # assert about. Reported by the skip counter rather than silent.
            self.skipTest("company is not on the Nepali chart")
        taxes = self.env["account.tax"].search([
            ("company_id", "=", self.company.id),
            ("amount", "=", 13.0),
            ("amount_type", "=", "percent"),
        ])
        self.assertTrue(taxes, "the np chart defines no 13% tax")
        for tax in taxes:
            with self.subTest(tax=tax.name, use=tax.type_tax_use):
                untagged = tax.repartition_line_ids.filtered(lambda r: not r.tag_ids)
                self.assertFalse(
                    untagged,
                    f"{tax.name} ({tax.type_tax_use}) has "
                    f"{len(untagged)} of {len(tax.repartition_line_ids)} repartition "
                    f"lines with no tax tag; the VAT return will compute this as nil "
                    f"(FIN-1). Re-apply the chart's tax data.")

    def test_box_from_tax_tags_ties_to_ledger(self):
        """A box must equal the ledger, to the rupee.

        Was `assertGreater(amount, 0)`, which a wrong sign or a partial sum would
        pass. 200,000 at 13% gives a 200,000 base and 26,000 of tax; summed with
        sign -1 over both tags that is exactly 226,000.
        """
        tax, tags = self._tagged_sale_tax()
        self.sale_tax = tax
        self._post_invoice(200000.0)

        form = self.Form.create({
            "name": "Test form", "date_from": "2026-07-17",
            "company_id": self.company.id,
            "box_ids": [Command.create({
                "code": "11", "label_en": "Taxable sales and VAT",
                "box_type": "tags", "sign": "-1",
                "tag_ids": [Command.set(tags.ids)],
            })],
        })
        ret = self.Return.create({
            "name": "VAT 2083-04", "date_from": "2026-07-17", "date_to": "2026-08-31",
            "company_id": self.company.id,
        })
        ret.action_compute()

        self.assertEqual(ret.state, "computed")
        self.assertEqual(ret.form_id, form, "the form version must be frozen on the return")
        line = ret.line_ids.filtered(lambda rl: rl.code == "11")
        self.assertTrue(line, "box 11 missing from the computed return")
        self.assertEqual(
            line.amount, 226000.0,
            "box 11 must equal base 200,000 plus tax 26,000 summed with sign -1; "
            f"got {line.amount}")

    def test_form_versioning(self):
        """A return must resolve the form that applied to its own period."""
        old = self.Form.create({
            "name": "Form v1", "date_from": "2025-07-17", "date_to": "2026-07-16",
            "company_id": self.company.id,
        })
        new = self.Form.create({
            "name": "Form v2", "date_from": "2026-07-17",
            "company_id": self.company.id,
        })
        self.assertEqual(
            self.Form._form_for_date(__import__("datetime").date(2026, 1, 10)), old)
        self.assertEqual(
            self.Form._form_for_date(__import__("datetime").date(2026, 9, 10)), new)

    def test_formula_box(self):
        form = self.Form.create({
            "name": "Formula form", "date_from": "2026-07-17",
            "company_id": self.company.id,
            "box_ids": [
                Command.create({"code": "A", "label_en": "A", "box_type": "formula",
                                "formula": "0"}),
                Command.create({"code": "NET", "label_en": "Net", "box_type": "formula",
                                "formula": "A + 5"}),
            ],
        })
        ret = self.Return.create({
            "name": "VAT formula", "date_from": "2026-07-17", "date_to": "2026-08-31",
            "company_id": self.company.id,
        })
        ret.action_compute()
        net = ret.line_ids.filtered(lambda rl: rl.code == "NET")
        self.assertAlmostEqual(net.amount, 5.0, places=2)
        self.assertTrue(form.id)

    def test_formula_rejects_arbitrary_code(self):
        """The formula grammar must not be a Python escape hatch."""
        self.Form.create({
            "name": "Bad formula", "date_from": "2026-07-17",
            "company_id": self.company.id,
            "box_ids": [Command.create({
                "code": "X", "label_en": "X", "box_type": "formula",
                "formula": "__import__('os').system('echo hi')",
            })],
        })
        ret = self.Return.create({
            "name": "VAT bad", "date_from": "2026-07-17", "date_to": "2026-08-31",
            "company_id": self.company.id,
        })
        with self.assertRaises(UserError):
            ret.action_compute()

    def test_tag_box_requires_tags(self):
        with self.assertRaises(ValidationError):
            self.Form.create({
                "name": "Empty tag box", "date_from": "2026-07-17",
                "company_id": self.company.id,
                "box_ids": [Command.create({
                    "code": "Z", "label_en": "Z", "box_type": "tags",
                })],
            })

    def test_period_order_validated(self):
        with self.assertRaises(ValidationError):
            self.Return.create({
                "name": "Bad period", "date_from": "2026-08-31", "date_to": "2026-07-17",
                "company_id": self.company.id,
            })

    def test_cannot_file_before_computing(self):
        ret = self.Return.create({
            "name": "VAT unfiled", "date_from": "2026-07-17", "date_to": "2026-08-31",
            "company_id": self.company.id,
        })
        with self.assertRaises(UserError):
            ret.action_file()
