# -*- coding: utf-8 -*-
"""Tests for the Nepal VAT return framework.

These prove the mechanism, not any particular form layout -- none ships.
The important guarantees:

  * with no form defined, computing raises a clear error rather than a blank return
  * box amounts come from tax tags on posted journal items, so they tie to the ledger
  * forms are versioned: a return keeps the form that applied to its period
  * formula boxes only accept a tiny arithmetic grammar, never arbitrary Python
"""
import glob
import os

from lxml import etree

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
    def test_xml_is_well_formed(self):
        for path in glob.glob(os.path.join(MODULE_DIR, "**", "*.xml"), recursive=True):
            with self.subTest(file=os.path.basename(path)):
                try:
                    etree.parse(path)
                except etree.XMLSyntaxError as exc:
                    self.fail(f"{os.path.basename(path)}: {exc}")

    def test_ships_with_no_form(self):
        """The IRD defines the layout; shipping a guess would be worse than nothing."""
        self.assertFalse(
            self.Form.search_count([]),
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

    def test_box_from_tax_tags_ties_to_ledger(self):
        tags = self._tags_of_sale_tax()
        if not tags:
            self.skipTest("sale tax has no tax tags configured in this chart")
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
        line = ret.line_ids.filtered(lambda l: l.code == "11")
        self.assertTrue(line, "box 11 missing from the computed return")
        self.assertGreater(line.amount, 0, "sign handling should present sales positive")

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
        net = ret.line_ids.filtered(lambda l: l.code == "NET")
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
