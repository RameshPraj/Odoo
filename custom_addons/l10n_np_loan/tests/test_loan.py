# -*- coding: utf-8 -*-
"""Tests for the loan amortisation schedule and its postings.

    venv\\Scripts\\python.exe -m odoo -c odoo.conf -d <db> \\
        --test-enable --test-tags /l10n_np_loan --stop-after-init

The assertion that matters most is that the schedule closes on exactly zero. A
loan that ends a few paisa out looks right on screen and leaves a balance on the
liability account that nobody can clear.
"""
import psycopg2
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestLoan(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create({"name": "NIC Asia Bank"})
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", cls.company.id)], limit=1)

        def account(code, name, account_type):
            existing = cls.env["account.account"].search(
                [("account_type", "=", account_type),
                 ("company_ids", "in", cls.company.id)], limit=1)
            if existing:
                return existing
            return cls.env["account.account"].create({
                "code": code, "name": name, "account_type": account_type,
                "company_ids": [(6, 0, [cls.company.id])],
            })

        cls.acc_loan = account("2400", "Loan payable", "liability_non_current")
        cls.acc_interest = account("6600", "Interest expense", "expense")
        cls.acc_bank = account("1100", "Bank", "asset_cash")

    def _loan(self, **overrides):
        values = {
            "name": "Test loan",
            "partner_id": self.partner.id,
            "principal": 1_200_000.0,
            "rate": 12.0,
            "date_start": "2026-07-16",
            "term": 12,
            "frequency": "monthly",
            "method": "emi",
            "journal_id": self.journal.id,
            "loan_account_id": self.acc_loan.id,
            "interest_account_id": self.acc_interest.id,
            "payment_account_id": self.acc_bank.id,
        }
        values.update(overrides)
        return self.env["l10n_np.loan"].create(values)

    # ---- the schedule closes ------------------------------------------------

    def test_emi_schedule_closes_on_zero(self):
        loan = self._loan()
        loan.action_compute_schedule()
        self.assertEqual(len(loan.line_ids), 12)
        self.assertEqual(loan.line_ids[-1].closing_balance, 0.0,
                         "an EMI schedule must end on exactly zero")

    def test_equal_principal_schedule_closes_on_zero(self):
        loan = self._loan(method="equal_principal")
        loan.action_compute_schedule()
        self.assertEqual(loan.line_ids[-1].closing_balance, 0.0)

    def test_interest_only_repays_everything_at_maturity(self):
        loan = self._loan(method="interest_only")
        loan.action_compute_schedule()
        self.assertEqual(loan.line_ids[-1].closing_balance, 0.0)
        self.assertEqual(sum(loan.line_ids[:-1].mapped("principal")), 0.0,
                         "interest-only must repay no principal before maturity")
        self.assertEqual(loan.line_ids[-1].principal, loan.principal,
                         "the whole principal falls due at maturity")

    def test_principal_repaid_equals_principal_borrowed(self):
        """Under every method, and with awkward numbers that will not divide."""
        for method in ("emi", "equal_principal", "interest_only"):
            loan = self._loan(method=method, principal=1_000_000.0,
                              rate=9.75, term=7)
            loan.action_compute_schedule()
            # Rounded to the currency: summing a dozen rounded monetary values in
            # Python accumulates float noise well below one paisa, which is not
            # a defect in the schedule.
            repaid = loan.currency_id.round(sum(loan.line_ids.mapped("principal")))
            self.assertEqual(
                repaid, loan.principal,
                f"{method}: repaid {repaid} against a principal of {loan.principal}")

    def test_each_row_is_internally_consistent(self):
        loan = self._loan(rate=13.5, term=9, principal=777_777.0)
        loan.action_compute_schedule()
        for line in loan.line_ids:
            self.assertAlmostEqual(
                line.payment, line.principal + line.interest, places=2,
                msg=f"row {line.sequence}: payment is not principal plus interest")
            self.assertAlmostEqual(
                line.closing_balance, line.opening_balance - line.principal,
                places=2, msg=f"row {line.sequence}: balance does not roll forward")

    def test_balances_chain_between_rows(self):
        loan = self._loan(rate=11.0, term=6)
        loan.action_compute_schedule()
        rows = loan.line_ids
        self.assertEqual(rows[0].opening_balance, loan.principal)
        # strict=False: rows[1:] is one shorter by construction, which is the
        # point -- each row is compared with its successor.
        for previous, current in zip(rows, rows[1:], strict=False):
            self.assertEqual(current.opening_balance, previous.closing_balance,
                             f"row {current.sequence} does not open where "
                             f"row {previous.sequence} closed")

    # ---- the awkward inputs -------------------------------------------------

    def test_zero_rate_loan_does_not_divide_by_zero(self):
        loan = self._loan(rate=0.0, term=10, principal=1_000_000.0)
        loan.action_compute_schedule()
        self.assertEqual(sum(loan.line_ids.mapped("interest")), 0.0)
        self.assertEqual(loan.line_ids[-1].closing_balance, 0.0)
        self.assertEqual(sum(loan.line_ids.mapped("principal")), 1_000_000.0)

    def test_single_instalment_loan(self):
        loan = self._loan(term=1)
        loan.action_compute_schedule()
        self.assertEqual(len(loan.line_ids), 1)
        self.assertEqual(loan.line_ids.principal, loan.principal)
        self.assertEqual(loan.line_ids.closing_balance, 0.0)

    def test_payment_below_interest_is_refused(self):
        """At an absurd rate the level payment never clears the principal.
        Say so instead of producing a schedule that grows forever."""
        loan = self._loan(rate=100000.0, term=240)
        with self.assertRaises(UserError) as caught:
            loan.action_compute_schedule()
        self.assertIn("never", str(caught.exception))

    def test_frequency_drives_the_dates_and_the_period_rate(self):
        monthly = self._loan(frequency="monthly", term=4, rate=12.0)
        quarterly = self._loan(frequency="quarterly", term=4, rate=12.0)
        monthly.action_compute_schedule()
        quarterly.action_compute_schedule()
        self.assertEqual(str(monthly.line_ids[0].date), "2026-08-16")
        self.assertEqual(str(quarterly.line_ids[0].date), "2026-10-16")
        self.assertGreater(quarterly.line_ids[0].interest,
                           monthly.line_ids[0].interest,
                           "a quarter accrues more interest than a month")

    def test_negative_principal_is_rejected(self):
        # CheckViolation, not Exception: the guard is the SQL constraint
        # CHECK(principal > 0), and `assertRaises(Exception)` would equally pass
        # on a typo in this test body (audit finding COD-7). Verified by running
        # it -- the ORM lets psycopg2's error through unwrapped here.
        with self.assertRaises(psycopg2.errors.CheckViolation):
            self._loan(principal=-1.0).flush_recordset()

    # ---- posting ------------------------------------------------------------

    def test_drawdown_entry_is_balanced_and_hits_the_liability(self):
        loan = self._loan()
        loan.action_confirm()
        loan.action_post_disbursement()
        move = loan.disbursement_move_id
        self.assertEqual(move.state, "posted")
        self.assertEqual(sum(move.line_ids.mapped("debit")),
                         sum(move.line_ids.mapped("credit")))
        liability = move.line_ids.filtered(
            lambda aml: aml.account_id == self.acc_loan)
        self.assertEqual(liability.credit, loan.principal,
                         "the drawdown must credit the loan account")

    def test_drawdown_cannot_be_posted_twice(self):
        loan = self._loan()
        loan.action_confirm()
        loan.action_post_disbursement()
        with self.assertRaises(UserError):
            loan.action_post_disbursement()

    def test_instalment_splits_principal_from_interest(self):
        loan = self._loan()
        loan.action_confirm()
        line = loan.line_ids[0]
        line.action_post()

        move = line.move_id
        self.assertEqual(move.state, "posted")
        self.assertEqual(sum(move.line_ids.mapped("debit")),
                         sum(move.line_ids.mapped("credit")))
        by_account = {aml.account_id: aml for aml in move.line_ids}
        self.assertEqual(by_account[self.acc_loan].debit, line.principal)
        self.assertEqual(by_account[self.acc_interest].debit, line.interest)
        self.assertEqual(by_account[self.acc_bank].credit, line.payment)

    def test_instalment_cannot_be_posted_twice(self):
        loan = self._loan()
        loan.action_confirm()
        loan.line_ids[0].action_post()
        with self.assertRaises(UserError) as caught:
            loan.line_ids[0].action_post()
        self.assertIn("already posted", str(caught.exception))

    def test_outstanding_follows_posted_instalments_only(self):
        loan = self._loan()
        loan.action_confirm()
        self.assertEqual(loan.outstanding, loan.principal,
                         "a scheduled instalment must not reduce the balance")
        first = loan.line_ids[0]
        first.action_post()
        self.assertEqual(loan.outstanding,
                         loan.currency_id.round(loan.principal - first.principal))

    def test_loan_closes_when_every_instalment_is_posted(self):
        loan = self._loan(term=2)
        loan.action_confirm()
        loan.line_ids.action_post()
        self.assertEqual(loan.state, "closed")
        self.assertEqual(loan.outstanding, 0.0,
                         "a fully repaid loan must leave nothing outstanding")

    def test_posting_requires_a_running_loan(self):
        loan = self._loan()
        loan.action_compute_schedule()
        self.assertEqual(loan.state, "draft")
        with self.assertRaises(UserError):
            loan.line_ids[0].action_post()

    def test_schedule_cannot_be_rebuilt_once_posted(self):
        """Rebuilding would orphan the entries already in the ledger."""
        loan = self._loan()
        loan.action_confirm()
        loan.line_ids[0].action_post()
        with self.assertRaises(UserError) as caught:
            loan.action_compute_schedule()
        self.assertIn("already posted", str(caught.exception))

    def test_posted_loan_cannot_be_cancelled(self):
        loan = self._loan()
        loan.action_confirm()
        loan.line_ids[0].action_post()
        with self.assertRaises(UserError):
            loan.action_cancel()

    def test_post_due_posts_only_what_has_fallen_due(self):
        today = fields.Date.context_today(self)
        loan = self._loan(date_start=today, term=6)
        loan.action_confirm()
        # Nothing is due yet: the first instalment is a month out.
        with self.assertRaises(UserError) as caught:
            loan.action_post_due()
        self.assertIn("No instalment is due", str(caught.exception))

        # Backdate so that exactly two instalments have fallen due.
        loan.line_ids[0].date = "2026-01-01"
        loan.line_ids[1].date = "2026-02-01"
        loan.action_post_due()
        states = loan.line_ids.mapped("state")
        self.assertEqual(states[:2], ["posted", "posted"])
        self.assertTrue(all(state == "draft" for state in states[2:]),
                        "instalments not yet due must stay scheduled")

    def test_interest_total_matches_the_schedule(self):
        loan = self._loan()
        loan.action_confirm()
        self.assertAlmostEqual(loan.total_interest,
                               sum(loan.line_ids.mapped("interest")), places=2)
        self.assertAlmostEqual(loan.total_payment,
                               loan.principal + loan.total_interest, places=2)
