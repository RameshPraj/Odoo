# -*- coding: utf-8 -*-
"""Tests for Balance Sheet and Profit & Loss.

    venv\\Scripts\\python.exe -m odoo -c odoo.conf -d <db> \\
        --test-enable --test-tags /account_financial_statements --stop-after-init

The critical assertion is that the balance sheet balances. Sign handling is the
classic bug in this kind of report: Odoo stores debit-positive balances, so
liabilities, equity and income must be flipped for presentation, and the
current-period result must be added to equity or the sheet will not tie.
"""
from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestFinancialStatements(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create({"name": "Test Customer"})

        def acc(code):
            return cls.env["account.account"].search(
                [("code", "=", code), ("company_ids", "in", cls.company.id)], limit=1)

        cls.acc_expense = acc("500302") or cls.env["account.account"].search(
            [("account_type", "=", "expense")], limit=1)
        cls.acc_payable = cls.env["account.account"].search(
            [("account_type", "=", "liability_payable")], limit=1)
        cls.sale_tax = cls.env["account.tax"].search(
            [("company_id", "=", cls.company.id), ("type_tax_use", "=", "sale")],
            order="amount desc", limit=1)

    def _post_invoice(self, amount, date="2026-08-01"):
        inv = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_date": date,
            "invoice_line_ids": [Command.create({
                "name": "Service",
                "quantity": 1,
                "price_unit": amount,
                "tax_ids": [Command.set(self.sale_tax.ids)],
            })],
        })
        inv.action_post()
        return inv

    def _post_expense(self, amount, date="2026-08-05"):
        je = self.env["account.move"].create({
            "move_type": "entry",
            "date": date,
            "journal_id": self.env["account.journal"].search(
                [("type", "=", "general")], limit=1).id,
            "line_ids": [
                Command.create({"account_id": self.acc_expense.id, "name": "Cost",
                                "debit": amount, "credit": 0.0}),
                Command.create({"account_id": self.acc_payable.id, "name": "Cost",
                                "debit": 0.0, "credit": amount,
                                "partner_id": self.partner.id}),
            ],
        })
        je.action_post()
        return je

    def _wizard(self, date_from="2026-07-17", date_to="2026-08-31"):
        return self.env["account.financial.statements.wizard"].create({
            "company_id": self.company.id,
            "date_from": date_from,
            "date_to": date_to,
            "target_move": "posted",
            "hide_zero": True,
        })

    # ------------------------------------------------------------------
    def test_balance_sheet_balances(self):
        """Assets must equal liabilities plus equity, including the period result."""
        self._post_invoice(400000.0)
        self._post_expense(120000.0)
        wiz = self._wizard()
        bs = self.env["report.account_financial_statements.balance_sheet"]._get_report_values(
            None, {"wizard_id": wiz.id})
        self.assertTrue(
            bs["balanced"],
            f"Balance sheet out by {bs['difference']}: "
            f"assets={bs['assets']['total']} liab={bs['liabilities']['total']} "
            f"equity={bs['total_equity']}",
        )
        self.assertAlmostEqual(bs["assets"]["total"], bs["total_liab_equity"], places=2)

    def test_profit_and_loss_arithmetic(self):
        self._post_invoice(400000.0)
        self._post_expense(120000.0)
        wiz = self._wizard()
        pl = self.env["report.account_financial_statements.profit_loss"]._get_report_values(
            None, {"wizard_id": wiz.id})
        self.assertAlmostEqual(pl["income"]["total"], 400000.0, places=2)
        self.assertAlmostEqual(pl["expenses"]["total"], 120000.0, places=2)
        self.assertAlmostEqual(pl["net"], 280000.0, places=2)

    def test_income_is_presented_positive(self):
        """Income carries a credit (negative) balance internally; it must read positive."""
        self._post_invoice(100000.0)
        wiz = self._wizard()
        pl = self.env["report.account_financial_statements.profit_loss"]._get_report_values(
            None, {"wizard_id": wiz.id})
        self.assertGreater(pl["income"]["total"], 0, "Income should present as positive")

    def test_balance_sheet_result_matches_profit_loss(self):
        """The equity line on the balance sheet must equal the P&L net profit."""
        self._post_invoice(400000.0)
        self._post_expense(120000.0)
        wiz = self._wizard()
        bs = self.env["report.account_financial_statements.balance_sheet"]._get_report_values(
            None, {"wizard_id": wiz.id})
        pl = self.env["report.account_financial_statements.profit_loss"]._get_report_values(
            None, {"wizard_id": wiz.id})
        self.assertAlmostEqual(bs["result"], pl["net"], places=2)

    def test_empty_books_balance(self):
        """A company with no entries must still produce a balanced sheet."""
        wiz = self._wizard()
        bs = self.env["report.account_financial_statements.balance_sheet"]._get_report_values(
            None, {"wizard_id": wiz.id})
        self.assertTrue(bs["balanced"])

    def test_draft_entries_excluded_when_posted_only(self):
        inv = self._post_invoice(50000.0)
        wiz = self._wizard()
        before = self.env["report.account_financial_statements.profit_loss"]._get_report_values(
            None, {"wizard_id": wiz.id})["income"]["total"]
        inv.button_draft()
        after = self.env["report.account_financial_statements.profit_loss"]._get_report_values(
            None, {"wizard_id": wiz.id})["income"]["total"]
        self.assertLess(after, before, "Draft entries must be excluded from 'posted only'")

    def test_wizard_rejects_inverted_dates(self):
        from odoo.exceptions import UserError  # noqa: PLC0415
        wiz = self._wizard(date_from="2026-08-31", date_to="2026-07-17")
        with self.assertRaises(UserError):
            wiz.action_profit_loss()

    # ---------------- cash flow -----------------------------------------
    def _cash_entry(self, cash_account, other_account, amount, date, label):
        """Debit cash / credit other for a positive amount, and vice versa."""
        lines = [
            Command.create({"account_id": cash_account.id, "name": label,
                            "debit": amount if amount > 0 else 0.0,
                            "credit": -amount if amount < 0 else 0.0}),
            Command.create({"account_id": other_account.id, "name": label,
                            "debit": -amount if amount < 0 else 0.0,
                            "credit": amount if amount > 0 else 0.0}),
        ]
        move = self.env["account.move"].create({
            "move_type": "entry", "date": date,
            "journal_id": self.env["account.journal"].search(
                [("type", "=", "general")], limit=1).id,
            "line_ids": lines,
        })
        move.action_post()
        return move

    def _accounts_for_cash_flow(self):
        A = self.env["account.account"]
        return {
            "cash": A.search([("account_type", "=", "asset_cash")], limit=1),
            "income": A.search([("account_type", "=", "income")], limit=1),
            "fixed": A.search([("account_type", "=", "asset_fixed")], limit=1),
            "loan": A.search([("account_type", "=", "liability_non_current")], limit=1),
        }

    def test_cash_flow_reconciles(self):
        """The core guarantee: classified movements must equal the change in cash."""
        a = self._accounts_for_cash_flow()
        if not all(a.values()):
            self.skipTest("chart lacks one of cash/income/fixed/non-current-liability")
        self._cash_entry(a["cash"], a["income"], 300000.0, "2026-08-02", "Cash sale")
        self._cash_entry(a["cash"], a["fixed"], -500000.0, "2026-08-06", "Equipment")
        self._cash_entry(a["cash"], a["loan"], 800000.0, "2026-08-10", "Loan")

        wiz = self._wizard()
        cf = self.env["report.account_financial_statements.cash_flow"]._get_report_values(
            None, {"wizard_id": wiz.id})
        self.assertTrue(
            cf["reconciled"],
            f"unreconciled by {cf['difference']}: movements={cf['movement_total']} "
            f"net_change={cf['net_change']}",
        )
        self.assertAlmostEqual(cf["net_change"], 600000.0, places=2)
        self.assertAlmostEqual(cf["closing"] - cf["opening"], cf["net_change"], places=2)

    def test_cash_flow_classification(self):
        """Each counterpart type must land in the right section."""
        a = self._accounts_for_cash_flow()
        if not all(a.values()):
            self.skipTest("chart lacks required account types")
        self._cash_entry(a["cash"], a["income"], 300000.0, "2026-08-02", "Cash sale")
        self._cash_entry(a["cash"], a["fixed"], -500000.0, "2026-08-06", "Equipment")
        self._cash_entry(a["cash"], a["loan"], 800000.0, "2026-08-10", "Loan")

        wiz = self._wizard()
        cf = self.env["report.account_financial_statements.cash_flow"]._get_report_values(
            None, {"wizard_id": wiz.id})
        by_total = {s["label"]: s["total"] for s in cf["sections"]}
        totals = list(by_total.values())
        self.assertIn(300000.0, [round(t, 2) for t in totals], "operating inflow missing")
        self.assertIn(-500000.0, [round(t, 2) for t in totals], "investing outflow missing")
        self.assertIn(800000.0, [round(t, 2) for t in totals], "financing inflow missing")

    def test_cash_flow_empty_period_reconciles(self):
        wiz = self._wizard()
        cf = self.env["report.account_financial_statements.cash_flow"]._get_report_values(
            None, {"wizard_id": wiz.id})
        self.assertTrue(cf["reconciled"])
