# -*- coding: utf-8 -*-
r"""Company A must not be able to read or edit company B's loans (SEC-2).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_loan --stop-after-init

Written against a real non-superuser, because record rules do not apply to the
superuser and `TransactionCase.env` is the superuser. A test that creates two
companies and merely checks `search()` as `self.env.user` would pass with no rules
installed at all -- it is the multi-company equivalent of the `search()`-based
menu-visibility mistake recorded in TESTING.md.

`with_company` alone is also not enough. It changes which company is *active*, not
which companies the user is *allowed*, and the rule filters on `company_ids`, which
comes from the latter. Only `with_user` exercises the rule.

Near-duplicated in l10n_np_tds and l10n_np_vat_return. No module depends on the
other two, so there is nowhere shared to put it; COD-2 already tracks this class of
copy-paste in the suite.
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestLoanCompanyIsolation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "SEC-2 Loan Co A"})
        cls.company_b = cls.env["res.company"].create({"name": "SEC-2 Loan Co B"})
        cls.partner = cls.env["res.partner"].create({"name": "SEC-2 Lender"})

        # A manager, not a limited user: the point is that even full CRUD rights on
        # the model must not reach another company's rows.
        cls.user_a = cls.env["res.users"].create({
            "name": "SEC-2 Loan Manager A",
            "login": "sec2_loan_a",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [(6, 0, [
                cls.env.ref("account.group_account_manager").id])],
        })

        cls.loan_a = cls._loan(cls.company_a)
        cls.loan_b = cls._loan(cls.company_b)

    @classmethod
    def _loan(cls, company):
        """A loan owned by `company`, created as superuser so no rule applies."""
        journal = cls.env["account.journal"].create({
            "name": f"SEC-2 {company.id}", "code": f"S2L{company.id}",
            "type": "general", "company_id": company.id,
        })

        def account(code, name, account_type):
            return cls.env["account.account"].create({
                "code": f"{code}{company.id}", "name": name,
                "account_type": account_type,
                "company_ids": [(6, 0, [company.id])],
            })

        return cls.env["l10n_np.loan"].create({
            "name": f"SEC-2 loan {company.name}",
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "partner_id": cls.partner.id,
            "principal": 1_000_000.0,
            "rate": 10.0,
            "date_start": "2026-07-16",
            "term": 12,
            "journal_id": journal.id,
            "loan_account_id": account("2400", "Loan payable",
                                       "liability_non_current").id,
            "interest_account_id": account("6600", "Interest", "expense").id,
            "payment_account_id": account("1100", "Bank", "asset_cash").id,
        })

    # ------------------------------------------------------------------
    def test_another_company_s_loan_is_not_searchable(self):
        found = self.env["l10n_np.loan"].with_user(self.user_a).search([])
        self.assertNotIn(self.loan_b, found,
                         "company B's loan is visible to a company A manager")

    def test_reading_another_company_s_loan_is_refused(self):
        with self.assertRaises(AccessError):
            self.loan_b.with_user(self.user_a).read(["name", "principal"])

    def test_editing_another_company_s_loan_is_refused(self):
        """The finding is 'read and edit'. Edit is the worse half: a loan's
        principal or rate silently rewritten is a misstatement, not a leak."""
        with self.assertRaises(AccessError):
            self.loan_b.with_user(self.user_a).write({"principal": 1.0})

    def test_own_company_s_loan_is_still_fully_usable(self):
        """The assertion that stops an over-broad rule.

        A domain of `[(0, '=', 1)]` would satisfy every test above and make the
        module useless. Same shape as the domestic-invoice guard in ACC-3.
        """
        as_a = self.loan_a.with_user(self.user_a)
        self.assertEqual(as_a.read(["name"])[0]["name"], self.loan_a.name)
        as_a.write({"rate": 11.0})
        self.assertEqual(as_a.rate, 11.0)
        self.assertIn(self.loan_a,
                      self.env["l10n_np.loan"].with_user(self.user_a).search([]))

    def test_schedule_lines_are_isolated_too(self):
        """The line model carries its own rule; a child row is a bypass otherwise."""
        self.loan_b.action_compute_schedule()
        self.assertTrue(self.loan_b.line_ids, "fixture: B's loan has a schedule")
        found = self.env["l10n_np.loan.line"].with_user(self.user_a).search([])
        self.assertFalse(found & self.loan_b.line_ids,
                         "company B's schedule lines are visible to company A")
