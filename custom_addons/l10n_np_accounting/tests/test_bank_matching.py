# -*- coding: utf-8 -*-
r"""Bank matching: clearing an outstanding payment against a bank statement line.

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_accounting --stop-after-init

The reported symptom was a customer receipt still sitting on the Balance Sheet
after the invoice had been paid. That was not a bug: the payment's outstanding
half waits for the bank to confirm it, and Community ships no screen to do the
confirming. This tests the screen that does.

Nothing here assigns `is_matched`. It is a stored compute off
`move_id.line_ids.amount_residual` (account_payment.py:469-497), so every state
below is built by really reconciling, and asserting on hand-set values would
test nothing.

Fixtures are searched-then-created, never searched-then-skipped (TST-3): a test
that quietly finds nothing to assert on is the failure mode this project has
already been bitten by four times.
"""
import re

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged("-at_install", "post_install")
class TestBankMatching(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create({"name": "Bank Matching Partner"})

        # The in-transit account, and a *different* one for suspense. They must
        # differ: `_seek_for_lines` classifies purely by account
        # (account_bank_statement_line.py:693-699), so if the outstanding account
        # were also the journal's suspense account the counterpart would stay
        # classified as a suspense line and nothing would ever read as resolved.
        cls.outstanding = cls._account(
            "asset_current", "NPBM_OUT", "Matching test outstanding", reconcile=True)
        cls.suspense = cls._account(
            "asset_current", "NPBM_SUS", "Matching test suspense", reconcile=True,
            exclude=cls.outstanding)
        cls.bank_account = cls._account("asset_cash", "NPBM_BNK", "Matching test bank")

        # A dedicated bank journal rather than the live one: the test needs to
        # know which suspense and outstanding accounts are in play, and writing
        # those onto a real journal would be reconfiguring the user's books.
        cls.bank_journal = cls.env["account.journal"].create({
            "name": "Matching Test Bank",
            "code": "NPBM",
            "type": "bank",
            "company_id": cls.company.id,
            "default_account_id": cls.bank_account.id,
            "suspense_account_id": cls.suspense.id,
        })
        # `outstanding_account_id` on a payment comes from the payment method line
        # (account_payment.py:620-623). Pinning it here is what makes the tests
        # deterministic: left alone, Community's create falls back to the chart's
        # own account (:913-915), which differs between databases.
        method_lines = (cls.bank_journal.inbound_payment_method_line_ids
                        | cls.bank_journal.outbound_payment_method_line_ids)
        method_lines.payment_account_id = cls.outstanding

    # ---- fixtures that cannot be absent (TST-3) --------------------------
    @classmethod
    def _account(cls, account_type, code, name, reconcile=False, exclude=None):
        # `reconcile` is matched in BOTH directions, not only when True. Searching
        # `asset_current` without it returned the first such account -- which is
        # `cls.outstanding`, flagged reconcile=True -- so the fixture meant to
        # supply a NON-reconcilable account handed back a reconcilable one and
        # `test_refuses_an_account_not_flagged_allow_reconciliation` asserted
        # against a database where the refusal was correctly not triggered.
        domain = [("account_type", "=", account_type),
                  ("company_ids", "in", cls.env.company.id),
                  ("reconcile", "=", reconcile)]
        if exclude:
            domain.append(("id", "!=", exclude.id))
        existing = cls.env["account.account"].search(domain, limit=1)
        if existing:
            return existing
        return cls.env["account.account"].create({
            "code": code, "name": name, "account_type": account_type,
            "reconcile": reconcile,
            "company_ids": [Command.set([cls.env.company.id])],
        })

    # ---- helpers ---------------------------------------------------------
    def _payment(self, amount=150.0, payment_type="inbound", post=True,
                 journal=None, **values):
        payment = self.env["account.payment"].create({
            "payment_type": payment_type,
            "partner_type": "customer" if payment_type == "inbound" else "supplier",
            "partner_id": self.partner.id,
            "amount": amount,
            "date": "2026-08-10",
            "journal_id": (journal or self.bank_journal).id,
            **values,
        })
        if post:
            payment.action_post()
        return payment

    def _statement_line(self, amount, ref="Bank credit", date="2026-08-12"):
        """A statement line in its virgin state: counterpart on suspense."""
        return self.env["account.bank.statement.line"].create({
            "journal_id": self.bank_journal.id,
            "date": date,
            "amount": amount,
            "payment_ref": ref,
        })

    def _wizard(self, payment=None, statement_line=None, **values):
        context = {}
        if payment is not None:
            context = {"active_model": "account.payment", "active_ids": payment.ids}
        elif statement_line is not None:
            context = {"active_model": "account.bank.statement.line",
                       "active_ids": statement_line.ids}
        return self.env["l10n_np.bank.matching"].with_context(**context).create(values)

    def _outstanding_line(self, payment):
        return payment.move_id.line_ids.filtered(
            lambda aml: aml.account_id == payment.outstanding_account_id)

    # ---- the happy paths -------------------------------------------------
    def test_create_mode_clears_the_payment(self):
        """The reported case: no statement exists, so the transaction is recorded."""
        payment = self._payment()
        self.assertFalse(payment.is_matched,
                         "fixture assumption: a payment through an outstanding "
                         "account starts unmatched")
        self.assertEqual(self._outstanding_line(payment).amount_residual, 150.0)

        wizard = self._wizard(payment=payment, mode="create", date="2026-08-12",
                              payment_ref="NCHL transfer")
        result = wizard.action_match()

        self.assertTrue(payment.is_matched)
        self.assertEqual(self._outstanding_line(payment).amount_residual, 0.0)

        st_line = self.env["account.bank.statement.line"].search(
            [("journal_id", "=", self.bank_journal.id),
             ("payment_ref", "=", "NCHL transfer")])
        self.assertEqual(len(st_line), 1)
        counterpart = st_line.move_id.line_ids.filtered(
            lambda aml: aml.account_id == self.outstanding)
        self.assertTrue(
            counterpart,
            "the counterpart must land on the outstanding account, not suspense: "
            "that is what create()'s counterpart_account_id key is for")
        self.assertFalse(
            st_line.move_id.line_ids.filtered(
                lambda aml: aml.account_id == self.suspense),
            "nothing should be left on suspense")
        self.assertTrue(st_line.is_reconciled)
        self.assertEqual(result["params"]["type"], "success")

    def test_existing_mode_resolves_and_matches(self):
        """The correct long-run workflow: the bank fact exists first."""
        payment = self._payment()
        st_line = self._statement_line(150.0)
        self.assertFalse(st_line.is_reconciled)
        self.assertTrue(
            st_line.move_id.line_ids.filtered(
                lambda aml: aml.account_id == self.suspense),
            "fixture assumption: a new statement line posts to suspense")

        wizard = self._wizard(payment=payment, mode="existing",
                              statement_line_id=st_line.id)
        wizard.action_match()

        self.assertTrue(payment.is_matched)
        self.assertEqual(self._outstanding_line(payment).amount_residual, 0.0)
        self.assertTrue(st_line.is_reconciled)
        self.assertFalse(
            st_line.move_id.line_ids.filtered(
                lambda aml: aml.account_id == self.suspense),
            "the suspense line should have been repointed, not duplicated")

    def test_an_outbound_payment_clears_the_same_way(self):
        """Signs are the other way round, and easy to get wrong in one direction."""
        payment = self._payment(payment_type="outbound")
        self.assertEqual(self._outstanding_line(payment).balance, -150.0)

        self._wizard(payment=payment, mode="create", date="2026-08-12").action_match()

        self.assertTrue(payment.is_matched)
        self.assertEqual(self._outstanding_line(payment).amount_residual, 0.0)

    def test_launching_from_the_bank_transaction_finds_the_payment(self):
        """From the statement-line side, with exactly one candidate."""
        payment = self._payment()
        st_line = self._statement_line(150.0)

        wizard = self._wizard(statement_line=st_line)
        self.assertEqual(wizard.payment_id, payment,
                         "one offsetting payment exists, so it should be filled in")
        self.assertEqual(wizard.mode, "existing")
        self.assertEqual(wizard.statement_line_id, st_line)

        wizard.action_match()
        self.assertTrue(payment.is_matched)

    def test_an_ambiguous_transaction_asks_rather_than_guesses(self):
        """Two payments for the same amount: filling one in would be a coin toss."""
        self._payment()
        self._payment()
        st_line = self._statement_line(150.0)

        wizard = self._wizard(statement_line=st_line)
        self.assertFalse(wizard.payment_id)
        with self.assertRaises(UserError) as caught:
            wizard.action_match()
        self.assertIn("Choose the payment", str(caught.exception))

    # ---- the symptom the user actually reported ---------------------------
    def test_the_balance_sheet_clears(self):
        """The Balance Sheet is where this was noticed, so assert it there.

        Asserting on `amount_residual` alone would have passed throughout the
        original complaint -- the residual was correct, the report was correctly
        showing it, and the user still had no way to clear it.
        """
        payment = self._payment()
        before = self._balance_sheet_amount(self.outstanding)
        self.assertAlmostEqual(
            before, 150.0, places=2,
            msg=f"fixture assumption: the outstanding receipt sits on the Balance "
                f"Sheet before matching, got {before}")

        self._wizard(payment=payment, mode="create", date="2026-08-12").action_match()

        after = self._balance_sheet_amount(self.outstanding)
        self.assertAlmostEqual(
            after, 0.0, places=2,
            msg=f"the outstanding account must be off the Balance Sheet, got {after}")
        self.assertAlmostEqual(
            self._balance_sheet_amount(self.bank_account), 150.0, places=2,
            msg="and the money must have arrived on the bank account")

    def _balance_sheet_amount(self, account):
        """One account's figure on the Balance Sheet, or 0.0 when it has dropped off.

        `hide_zero` is on by default, so a cleared account is absent rather than
        zero -- which is the same statement as far as this test is concerned.
        """
        wizard = self.env["account.financial.statements.wizard"].create({
            "report_type": "balance_sheet",
            "company_id": self.company.id,
            "date_from": "2026-07-17",
            "date_to": "2026-08-31",
        })
        report = self.env["report.account_financial_statements.balance_sheet"]
        values = report._get_report_values(None, {"wizard_id": wizard.id})
        for block in values["assets"]["blocks"]:
            for line in block["lines"]:
                if line["account_id"] == account.id:
                    return line["amount"]
        return 0.0

    # ---- refusals, one per rung ------------------------------------------
    def test_refuses_a_payment_with_no_journal_entry(self):
        payment = self._payment(post=False)
        wizard = self._wizard(payment=payment, mode="create", date="2026-08-12")
        with self.assertRaises(UserError) as caught:
            wizard.action_match()
        self.assertIn("no journal entry", str(caught.exception))

    def test_refuses_a_payment_that_is_already_matched(self):
        payment = self._payment()
        self._wizard(payment=payment, mode="create", date="2026-08-12").action_match()
        self.assertTrue(payment.is_matched)

        wizard = self._wizard(payment=payment, mode="create", date="2026-08-13")
        with self.assertRaises(UserError) as caught:
            wizard.action_match()
        self.assertIn("already matched", str(caught.exception))

    def test_refuses_a_payment_with_no_outstanding_account(self):
        """It posts straight to the bank, so there is no in-transit step at all."""
        payment = self._payment()
        payment.outstanding_account_id = False
        wizard = self._wizard(payment=payment, mode="create", date="2026-08-12")
        with self.assertRaises(UserError) as caught:
            wizard.action_match()
        self.assertIn("does not use an outstanding account", str(caught.exception))

    def test_refuses_an_account_not_flagged_allow_reconciliation(self):
        payment = self._payment()
        # Repointed rather than un-flagging the real account, which would fail on
        # the reconciled lines already sitting there.
        payment.outstanding_account_id = self._account(
            "asset_current", "NPBM_NOREC", "Matching test not reconcilable")
        wizard = self._wizard(payment=payment, mode="create", date="2026-08-12")
        with self.assertRaises(UserError) as caught:
            wizard.action_match()
        self.assertIn("Allow Reconciliation", str(caught.exception))

    def test_refuses_a_foreign_currency_payment(self):
        """ACC-1. Refused with a sentence rather than approximated at the wrong rate."""
        foreign = self.env["res.currency"].with_context(active_test=False).search(
            [("id", "!=", self.company.currency_id.id)], limit=1)
        foreign.active = True
        journal = self.env["account.journal"].create({
            "name": "Matching Test Foreign Bank", "code": "NPBF", "type": "bank",
            "company_id": self.company.id,
            "currency_id": foreign.id,
            "default_account_id": self.bank_account.id,
            "suspense_account_id": self.suspense.id,
        })
        (journal.inbound_payment_method_line_ids
         | journal.outbound_payment_method_line_ids).payment_account_id = self.outstanding
        payment = self._payment(journal=journal)

        wizard = self._wizard(payment=payment, mode="create", date="2026-08-12")
        with self.assertRaises(UserError) as caught:
            wizard.action_match()
        self.assertIn("company-currency payments only", str(caught.exception))

    def test_refuses_amounts_that_do_not_offset(self):
        payment = self._payment(amount=150.0)
        st_line = self._statement_line(200.0)
        wizard = self._wizard(payment=payment, mode="existing",
                              statement_line_id=st_line.id)
        with self.assertRaises(UserError) as caught:
            wizard.action_match()
        self.assertIn("do not offset", str(caught.exception))

    def test_refuses_a_transaction_that_is_already_resolved(self):
        """Two payments, one transaction: the second must be told, not silently mangled."""
        first = self._payment()
        second = self._payment()
        st_line = self._statement_line(150.0)
        self._wizard(payment=first, mode="existing",
                     statement_line_id=st_line.id).action_match()

        wizard = self._wizard(payment=second, mode="existing",
                              statement_line_id=st_line.id)
        with self.assertRaises(UserError) as caught:
            wizard.action_match()
        self.assertIn("already been resolved", str(caught.exception))

    def test_refuses_a_transaction_on_another_journal(self):
        payment = self._payment()
        other = self.env["account.journal"].create({
            "name": "Matching Test Other Bank", "code": "NPBO", "type": "bank",
            "company_id": self.company.id,
            "default_account_id": self.bank_account.id,
            "suspense_account_id": self.suspense.id,
        })
        st_line = self.env["account.bank.statement.line"].create({
            "journal_id": other.id, "date": "2026-08-12", "amount": 150.0,
            "payment_ref": "Wrong journal",
        })
        wizard = self._wizard(payment=payment, mode="existing",
                              statement_line_id=st_line.id)
        with self.assertRaises(UserError) as caught:
            wizard.action_match()
        self.assertIn("bank journal", str(caught.exception))

    def test_refuses_to_open_from_an_unrelated_model(self):
        with self.assertRaises(UserError) as caught:
            self.env["l10n_np.bank.matching"].with_context(
                active_model="res.partner", active_ids=self.partner.ids).create({})
        self.assertIn("cannot be opened from", str(caught.exception))

    # ---- the edit guard ---------------------------------------------------
    def test_editing_a_matched_transaction_is_refused(self):
        """Without this the match dissolves silently.

        `_synchronize_to_moves` rebuilds `line_ids` and unlinks every non-suspense
        line; `account_move_line.unlink` begins with `remove_move_reconcile()`. No
        error is raised by core, and the payment goes back to unmatched.
        """
        payment = self._payment()
        st_line = self._statement_line(150.0)
        self._wizard(payment=payment, mode="existing",
                     statement_line_id=st_line.id).action_match()

        other_partner = self.env["res.partner"].create({"name": "Someone Else"})
        with self.assertRaises(UserError) as caught:
            st_line.write({"partner_id": other_partner.id})
        self.assertIn("would rebuild the journal entry", str(caught.exception))
        self.assertTrue(payment.is_matched, "and the match must still stand")

    def test_editing_an_unmatched_transaction_still_works(self):
        """The negative control. Without it the guard could refuse everything."""
        st_line = self._statement_line(150.0)
        other_partner = self.env["res.partner"].create({"name": "Someone Else"})

        st_line.write({"partner_id": other_partner.id})

        self.assertEqual(st_line.partner_id, other_partner)
        self.assertTrue(
            st_line.move_id.line_ids.filtered(
                lambda aml: aml.account_id == self.suspense),
            "core's sync should have rebuilt the suspense line as normal")

    def test_the_guard_covers_every_field_core_syncs_on(self):
        """Two sources of truth for the same list, so something has to compare them.

        If core adds a seventh trigger field, the guard silently stops covering it
        and the silent-destruction path reopens.
        """
        import odoo.addons.account.models.account_bank_statement_line as core

        with open(core.__file__, encoding="utf-8") as handle:
            source = handle.read()
        body = source.split("def _synchronize_to_moves", 1)[1]
        guard = body.split("for st_line in self", 1)[0]
        in_core = set(re.findall(r"'(\w+)'", guard)) - {
            "skip_account_move_synchronization"}

        in_module = set(self.env["account.bank.statement.line"]._SYNC_TRIGGER_FIELDS)
        self.assertEqual(
            in_core, in_module,
            f"core syncs on {sorted(in_core)} but the guard covers "
            f"{sorted(in_module)}; an uncovered field silently undoes matches")

    # ---- reversing a match ------------------------------------------------
    def test_unmatch_round_trips(self):
        payment = self._payment()
        st_line = self._statement_line(150.0)
        self._wizard(payment=payment, mode="existing",
                     statement_line_id=st_line.id).action_match()
        self.assertTrue(payment.is_matched)

        st_line.action_unmatch()

        self.assertFalse(payment.is_matched)
        self.assertEqual(self._outstanding_line(payment).amount_residual, 150.0)
        self.assertTrue(
            st_line.move_id.line_ids.filtered(
                lambda aml: aml.account_id == self.suspense),
            "the counterpart must go back to suspense, ready to be matched again")
        self.assertFalse(st_line.is_reconciled)

        # And it can be matched again, which is the half that proves the reset
        # was clean rather than merely unreconciled.
        self._wizard(payment=payment, mode="existing",
                     statement_line_id=st_line.id).action_match()
        self.assertTrue(payment.is_matched)

    def test_unmatch_refuses_a_transaction_that_is_not_matched(self):
        st_line = self._statement_line(150.0)
        with self.assertRaises(UserError) as caught:
            st_line.action_unmatch()
        self.assertIn("not matched to anything", str(caught.exception))

    # ---- properties the design promised -----------------------------------
    def test_the_payment_link_is_derived_not_stored(self):
        """`payment_ids` must stay empty, because core's undo unlinks what is in it.

        `action_undo_reconciliation` does `self.payment_ids.unlink()`
        (account_bank_statement_line.py:465). Anything written there turns a
        reset button into a delete-the-payment button. Core already derives the
        link from the reconciliation itself, so nothing needs storing.
        """
        payment = self._payment()
        st_line = self._statement_line(150.0)
        self._wizard(payment=payment, mode="existing",
                     statement_line_id=st_line.id).action_match()

        self.assertFalse(st_line.payment_ids,
                         "nothing may be written to payment_ids")
        self.assertIn(st_line, payment.reconciled_statement_line_ids,
                      "and the link is still visible, because core computes it")

    def test_the_transaction_action_domain_lists_only_bank_transactions(self):
        action = self.env.ref("l10n_np_accounting.action_bank_statement_line")
        listed = self.env["account.bank.statement.line"].search(
            safe_eval(action.domain))
        self.assertFalse(listed.filtered(
            lambda line: line.journal_id.type not in ("bank", "cash", "credit")))

    def test_the_transaction_views_exist(self):
        """Community defines none, so these are the first. If they vanish, the
        three core actions that open this model fall back to generated views."""
        for suffix in ("list", "search", "form"):
            view = self.env.ref(f"l10n_np_accounting.view_bank_statement_line_{suffix}")
            self.assertEqual(view.model, "account.bank.statement.line")
        arch = self.env.ref(
            "l10n_np_accounting.view_bank_statement_line_list").get_combined_arch()
        self.assertIn('name="action_l10n_np_match_payment"', arch)
        self.assertIn('name="action_unmatch"', arch)

    def test_the_payment_form_offers_the_button(self):
        arch = self.env.ref("account.view_account_payment_form").get_combined_arch()
        self.assertIn('name="action_l10n_np_match_to_bank"', arch)
