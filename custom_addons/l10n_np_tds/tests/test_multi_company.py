# -*- coding: utf-8 -*-
r"""Company A must not reach company B's TDS records (SEC-2).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_tds --stop-after-init

Uses `with_user` with a real non-superuser: record rules never apply to the
superuser, and `TransactionCase.env` is the superuser, so a check run as
`self.env.user` would pass with no rules installed at all. See the fuller note in
l10n_np_loan/tests/test_multi_company.py, of which this is a near-duplicate --
no module depends on the other, so there is nowhere shared to put it.

A withholding certificate is a document handed to a payee and filed with the IRD.
Cross-company visibility here is a disclosure of a third party's tax affairs, not
only an internal permissions error.
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestTdsCompanyIsolation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "SEC-2 TDS Co A"})
        cls.company_b = cls.env["res.company"].create({"name": "SEC-2 TDS Co B"})
        cls.partner = cls.env["res.partner"].create({"name": "SEC-2 Payee"})

        cls.user_a = cls.env["res.users"].create({
            "name": "SEC-2 TDS Manager A",
            "login": "sec2_tds_a",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [(6, 0, [
                cls.env.ref("account.group_account_manager").id])],
        })

        cls.records_a = cls._records(cls.company_a)
        cls.records_b = cls._records(cls.company_b)

    @classmethod
    def _records(cls, company):
        """One record of every company-scoped TDS model, owned by `company`."""
        account = cls.env["account.account"].create({
            "code": f"2450{company.id}", "name": "TDS payable",
            "account_type": "liability_current",
            "company_ids": [(6, 0, [company.id])],
        })
        category = cls.env["l10n_np.tds.category"].create({
            "name": "Service fee", "code": f"SVC{company.id}",
            "company_id": company.id, "rate": 1.5,
            "date_from": "2026-07-16", "account_id": account.id,
        })
        certificate = cls.env["l10n_np.tds.certificate"].create({
            "partner_id": cls.partner.id, "company_id": company.id,
            "date_from": "2026-07-16", "date_to": "2027-07-15",
        })
        line = cls.env["l10n_np.tds.certificate.line"].create({
            "certificate_id": certificate.id, "name": "Consultancy",
            "date": "2026-08-01", "category_id": category.id,
            "amount_base": 100_000.0, "amount_tds": 1_500.0,
        })
        tds_return = cls.env["l10n_np.tds.return"].create({
            "name": f"SEC-2 return {company.id}", "company_id": company.id,
            "date_from": "2026-07-16", "date_to": "2027-07-15",
        })
        return {
            "l10n_np.tds.category": category,
            "l10n_np.tds.certificate": certificate,
            "l10n_np.tds.certificate.line": line,
            "l10n_np.tds.return": tds_return,
        }

    # ------------------------------------------------------------------
    def test_no_tds_record_of_another_company_is_searchable(self):
        for model, record in self.records_b.items():
            with self.subTest(model=model):
                found = self.env[model].with_user(self.user_a).search([])
                self.assertNotIn(record, found,
                                 f"company B's {model} is visible to company A")

    def test_reading_another_company_s_tds_record_is_refused(self):
        for model, record in self.records_b.items():
            with self.subTest(model=model):
                with self.assertRaises(AccessError):
                    record.with_user(self.user_a).read(["display_name"])

    def test_editing_another_company_s_certificate_is_refused(self):
        """A filed certificate rewritten by another company's staff is the
        finding's 'and edit' half, and the one with statutory consequences."""
        with self.assertRaises(AccessError):
            self.records_b["l10n_np.tds.certificate"].with_user(
                self.user_a).write({"date_to": "2027-01-01"})

    def test_own_company_s_tds_records_are_still_usable(self):
        """Guards against an over-broad rule, which would pass every test above
        while making the module unusable."""
        for model, record in self.records_a.items():
            with self.subTest(model=model):
                as_a = record.with_user(self.user_a)
                self.assertTrue(as_a.read(["display_name"]))
                self.assertIn(record,
                              self.env[model].with_user(self.user_a).search([]))
