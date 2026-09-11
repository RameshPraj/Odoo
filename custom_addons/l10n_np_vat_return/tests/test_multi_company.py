# -*- coding: utf-8 -*-
r"""Company A must not reach company B's VAT returns (SEC-2).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_vat_return --stop-after-init

Uses `with_user` with a real non-superuser: record rules never apply to the
superuser, and `TransactionCase.env` is the superuser, so the same check run as
`self.env.user` would pass with no rules installed. Fuller note in
l10n_np_loan/tests/test_multi_company.py, of which this is a near-duplicate.

Two of the four models here, the box and the line, had **no `company_id` at all**,
so SEC-2's premise that a rule could simply be added was wrong for them. Each now
carries a stored related `company_id`. The box test is therefore also a test that
the new field is populated: an empty `company_id` would make the rule match
nothing and these tests would fail closed, which is the right direction to fail.
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestVatReturnCompanyIsolation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "SEC-2 VAT Co A"})
        cls.company_b = cls.env["res.company"].create({"name": "SEC-2 VAT Co B"})

        cls.user_a = cls.env["res.users"].create({
            "name": "SEC-2 VAT Manager A",
            "login": "sec2_vat_a",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [(6, 0, [
                cls.env.ref("account.group_account_manager").id])],
        })

        cls.records_a = cls._records(cls.company_a)
        cls.records_b = cls._records(cls.company_b)

    @classmethod
    def _records(cls, company):
        """One record of every company-scoped model, owned by `company`."""
        form = cls.env["l10n_np.vat.return.form"].create({
            "name": f"SEC-2 form {company.id}", "company_id": company.id,
            "date_from": "2026-07-16",
        })
        # box_type 'heading' deliberately: a 'tags' box must carry tax tags, and
        # this test is about ownership, not about the box definition.
        box = cls.env["l10n_np.vat.return.box"].create({
            "form_id": form.id, "code": "11", "label_en": "Taxable sales",
            "box_type": "heading",
        })
        vat_return = cls.env["l10n_np.vat.return"].create({
            "name": f"SEC-2 return {company.id}", "company_id": company.id,
            "date_from": "2026-07-16", "date_to": "2026-08-16",
        })
        line = cls.env["l10n_np.vat.return.line"].create({
            "return_id": vat_return.id, "code": "11", "label_en": "Taxable sales",
            "amount": 100_000.0,
        })
        return {
            "l10n_np.vat.return.form": form,
            "l10n_np.vat.return.box": box,
            "l10n_np.vat.return": vat_return,
            "l10n_np.vat.return.line": line,
        }

    # ------------------------------------------------------------------
    def test_the_new_company_id_fields_are_populated(self):
        """The rule can only work if the stored related field actually resolved."""
        self.assertEqual(self.records_a["l10n_np.vat.return.box"].company_id,
                         self.company_a)
        self.assertEqual(self.records_a["l10n_np.vat.return.line"].company_id,
                         self.company_a)

    def test_no_vat_record_of_another_company_is_searchable(self):
        for model, record in self.records_b.items():
            with self.subTest(model=model):
                found = self.env[model].with_user(self.user_a).search([])
                self.assertNotIn(record, found,
                                 f"company B's {model} is visible to company A")

    def test_reading_another_company_s_vat_record_is_refused(self):
        for model, record in self.records_b.items():
            with self.subTest(model=model), self.assertRaises(AccessError):
                record.with_user(self.user_a).read(["display_name"])

    def test_editing_another_company_s_filed_return_is_refused(self):
        """The most sensitive write in this repo: a filed statutory return."""
        with self.assertRaises(AccessError):
            self.records_b["l10n_np.vat.return"].with_user(
                self.user_a).write({"name": "tampered"})

    def test_editing_another_company_s_return_line_is_refused(self):
        """The figures themselves, reachable without touching the return."""
        with self.assertRaises(AccessError):
            self.records_b["l10n_np.vat.return.line"].with_user(
                self.user_a).write({"amount": 0.0})

    def test_own_company_s_vat_records_are_still_usable(self):
        """Guards against an over-broad rule, which would pass every test above
        while making the module unusable."""
        for model, record in self.records_a.items():
            with self.subTest(model=model):
                as_a = record.with_user(self.user_a)
                self.assertTrue(as_a.read(["display_name"]))
                self.assertIn(record,
                              self.env[model].with_user(self.user_a).search([]))
