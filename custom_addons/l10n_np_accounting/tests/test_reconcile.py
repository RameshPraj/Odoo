# -*- coding: utf-8 -*-
"""Tests for the Reconcile button.

The button is a thin shell over Community's own ``account.move.line.reconcile()``.
What is worth testing is the shell: that it refuses the selections the engine
cannot handle, with a sentence rather than a traceback, and that a valid
selection really does end up reconciled.
"""
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged("-at_install", "post_install")
class TestReconcileButton(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls._journal()
        cls.receivable = cls._account(
            "asset_receivable", "TST3RECV", "Test receivable", reconcile=True)
        cls.income = cls._account("income", "TST3INC", "Test income")
        cls.payable = cls._account(
            "liability_payable", "TST3PAY", "Test payable", reconcile=True)
        cls.partner = cls.env["res.partner"].create({"name": "Reconcile Test Partner"})

    # ---- fixtures that cannot be absent (TST-3) --------------------------
    #
    # These were `search(...)` against the live company, and every test that
    # needed one called `_skip_unless_chart()` when it came back empty. On a
    # database whose chart differs -- a fresh install, a company created for
    # another test, a future chart revision -- six of the seven tests here
    # skipped, and the suite reported success for a class that had asserted
    # almost nothing. Nothing printed the skip count either, so a run of nothing
    # was indistinguishable from a run that passed.
    #
    # Searched first, created if missing: an existing chart is still used where
    # it exists, so the tests stay representative, but they can no longer be
    # silenced by its absence.

    @classmethod
    def _account(cls, account_type, code, name, reconcile=False):
        domain = [("account_type", "=", account_type),
                  ("company_ids", "in", cls.env.company.id)]
        if reconcile:
            domain.append(("reconcile", "=", True))
        existing = cls.env["account.account"].search(domain, limit=1)
        if existing:
            return existing
        return cls.env["account.account"].create({
            "code": code, "name": name, "account_type": account_type,
            "reconcile": reconcile,
            "company_ids": [Command.set([cls.env.company.id])],
        })

    @classmethod
    def _journal(cls):
        existing = cls.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", cls.env.company.id)], limit=1)
        if existing:
            return existing
        return cls.env["account.journal"].create({
            "name": "TST-3 General", "code": "TST3G", "type": "general",
            "company_id": cls.env.company.id,
        })

    def _entry(self, debit_account, credit_account, amount, date="2026-08-10"):
        move = self.env["account.move"].create({
            "move_type": "entry",
            "date": date,
            "journal_id": self.journal.id,
            "line_ids": [
                Command.create({"account_id": debit_account.id, "name": "d",
                                "debit": amount, "credit": 0.0,
                                "partner_id": self.partner.id}),
                Command.create({"account_id": credit_account.id, "name": "c",
                                "debit": 0.0, "credit": amount,
                                "partner_id": self.partner.id}),
            ],
        })
        return move

    def test_refuses_fewer_than_two_lines(self):
        model = self.env["account.move.line"]
        with self.assertRaises(UserError) as caught:
            model.browse([]).action_reconcile_selected()
        self.assertIn("at least two", str(caught.exception))

    def test_refuses_draft_entries(self):
        move = self._entry(self.receivable, self.income, 1000.0)
        lines = move.line_ids
        with self.assertRaises(UserError) as caught:
            lines.action_reconcile_selected()
        self.assertIn("posted", str(caught.exception))

    def test_refuses_non_reconcilable_account(self):
        move = self._entry(self.receivable, self.income, 1000.0)
        move.action_post()
        with self.assertRaises(UserError) as caught:
            move.line_ids.action_reconcile_selected()
        # The income leg is not reconcilable, so that check fires before the
        # single-account check.
        self.assertIn("Allow", str(caught.exception))

    def test_refuses_two_different_accounts(self):
        other = self.payable
        first = self._entry(self.receivable, self.income, 1000.0)
        second = self._entry(self.income, other, 1000.0)
        (first + second).action_post()
        lines = (first.line_ids + second.line_ids).filtered(
            lambda line: line.account_id.reconcile)
        with self.assertRaises(UserError) as caught:
            lines.action_reconcile_selected()
        self.assertIn("one account", str(caught.exception))

    def test_reconciles_an_offsetting_pair(self):
        debit_side = self._entry(self.receivable, self.income, 1000.0)
        credit_side = self._entry(self.income, self.receivable, 1000.0)
        (debit_side + credit_side).action_post()
        lines = (debit_side.line_ids + credit_side.line_ids).filtered(
            lambda line: line.account_id == self.receivable)
        self.assertEqual(len(lines), 2)

        result = lines.action_reconcile_selected()

        self.assertTrue(all(lines.mapped("reconciled")),
                        "an exactly offsetting pair must end fully reconciled")
        self.assertEqual(result["params"]["type"], "success")

    def test_refuses_already_reconciled_lines(self):
        debit_side = self._entry(self.receivable, self.income, 1000.0)
        credit_side = self._entry(self.income, self.receivable, 1000.0)
        (debit_side + credit_side).action_post()
        lines = (debit_side.line_ids + credit_side.line_ids).filtered(
            lambda line: line.account_id == self.receivable)
        lines.action_reconcile_selected()
        with self.assertRaises(UserError) as caught:
            lines.action_reconcile_selected()
        self.assertIn("already", str(caught.exception))

    def test_action_domain_shows_only_open_reconcilable_items(self):
        """The Reconcile screen must not list closed or unreconcilable items."""
        action = self.env.ref("l10n_np_accounting.action_account_reconcile")
        listed = self.env["account.move.line"].search(safe_eval(action.domain))
        self.assertFalse(listed.filtered(lambda line: not line.account_id.reconcile))
        self.assertFalse(listed.filtered(lambda line: line.parent_state != "posted"))
        self.assertFalse(listed.filtered(lambda line: not line.amount_residual))
