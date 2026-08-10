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
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", cls.env.company.id)], limit=1)
        cls.receivable = cls.env["account.account"].search(
            [("account_type", "=", "asset_receivable"),
             ("reconcile", "=", True),
             ("company_ids", "in", cls.env.company.id)], limit=1)
        cls.income = cls.env["account.account"].search(
            [("account_type", "=", "income"),
             ("company_ids", "in", cls.env.company.id)], limit=1)
        cls.partner = cls.env["res.partner"].create({"name": "Reconcile Test Partner"})

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

    def _skip_unless_chart(self):
        if not (self.journal and self.receivable and self.income):
            self.skipTest("company has no chart of accounts loaded")

    def test_refuses_fewer_than_two_lines(self):
        model = self.env["account.move.line"]
        with self.assertRaises(UserError) as caught:
            model.browse([]).action_reconcile_selected()
        self.assertIn("at least two", str(caught.exception))

    def test_refuses_draft_entries(self):
        self._skip_unless_chart()
        move = self._entry(self.receivable, self.income, 1000.0)
        lines = move.line_ids
        with self.assertRaises(UserError) as caught:
            lines.action_reconcile_selected()
        self.assertIn("posted", str(caught.exception))

    def test_refuses_non_reconcilable_account(self):
        self._skip_unless_chart()
        move = self._entry(self.receivable, self.income, 1000.0)
        move.action_post()
        with self.assertRaises(UserError) as caught:
            move.line_ids.action_reconcile_selected()
        # The income leg is not reconcilable, so that check fires before the
        # single-account check.
        self.assertIn("Allow", str(caught.exception))

    def test_refuses_two_different_accounts(self):
        self._skip_unless_chart()
        other = self.env["account.account"].search(
            [("account_type", "=", "liability_payable"), ("reconcile", "=", True),
             ("company_ids", "in", self.env.company.id)], limit=1)
        if not other:
            self.skipTest("no second reconcilable account")
        first = self._entry(self.receivable, self.income, 1000.0)
        second = self._entry(self.income, other, 1000.0)
        (first + second).action_post()
        lines = (first.line_ids + second.line_ids).filtered(
            lambda line: line.account_id.reconcile)
        with self.assertRaises(UserError) as caught:
            lines.action_reconcile_selected()
        self.assertIn("one account", str(caught.exception))

    def test_reconciles_an_offsetting_pair(self):
        self._skip_unless_chart()
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
        self._skip_unless_chart()
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
        self._skip_unless_chart()
        action = self.env.ref("l10n_np_accounting.action_account_reconcile")
        listed = self.env["account.move.line"].search(safe_eval(action.domain))
        self.assertFalse(listed.filtered(lambda line: not line.account_id.reconcile))
        self.assertFalse(listed.filtered(lambda line: line.parent_state != "posted"))
        self.assertFalse(listed.filtered(lambda line: not line.amount_residual))
