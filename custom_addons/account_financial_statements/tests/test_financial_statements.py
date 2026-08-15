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
from odoo.tools.safe_eval import safe_eval


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
        """Assert the DELTA this test causes, not the company-wide total.

        The P&L sums every posted line for the company in the period, so an
        absolute assertion silently depends on the database being empty of other
        income -- and it stopped being true the moment somebody used the app,
        failing with 400150.0 != 400000.0 over 150.00 of unrelated invoicing.
        That is audit finding TST-2. Measuring before and after keeps the real
        subject of the test -- that net = income - expenses -- and makes it
        independent of whatever else is in the books.
        """
        pl_model = self.env["report.account_financial_statements.profit_loss"]
        wiz = self._wizard()
        before = pl_model._get_report_values(None, {"wizard_id": wiz.id})

        self._post_invoice(400000.0)
        self._post_expense(120000.0)
        after = pl_model._get_report_values(None, {"wizard_id": wiz.id})

        self.assertAlmostEqual(
            after["income"]["total"] - before["income"]["total"], 400000.0, places=2)
        self.assertAlmostEqual(
            after["expenses"]["total"] - before["expenses"]["total"], 120000.0, places=2)
        self.assertAlmostEqual(
            after["net"] - before["net"], 280000.0, places=2)
        # The identities themselves, on the absolute figures: these must hold
        # whatever else the books contain. Note `cost_of_sales` is a section in
        # its own right -- `expenses` covers only 'expense' and
        # 'expense_depreciation' -- so net is income minus BOTH.
        self.assertAlmostEqual(
            after["gross"],
            after["income"]["total"] - after["cost_of_sales"]["total"],
            places=2, msg="gross profit must be income less cost of sales")
        self.assertAlmostEqual(
            after["net"], after["gross"] - after["expenses"]["total"],
            places=2, msg="net must be gross profit less operating expenses")

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


@tagged("-at_install", "post_install")
class TestStatementActions(TransactionCase):
    """The three Reporting menu items must each open the wizard pre-aimed.

    Enterprise presents Balance Sheet, Profit and Loss and Cash Flow as three
    separate reports. Here they share one wizard, so each menu item carries its
    own action whose context presets ``report_type``. If that wiring breaks the
    menus silently all print the same statement, which is the kind of bug nobody
    notices until a filing is wrong.
    """

    PRESETS = {
        "action_balance_sheet": "balance_sheet",
        "action_profit_loss": "profit_loss",
        "action_cash_flow": "cash_flow",
    }

    def test_each_action_presets_its_statement(self):
        for xmlid, expected in self.PRESETS.items():
            action = self.env.ref(f"account_financial_statements.{xmlid}")
            wizard = self.env["account.financial.statements.wizard"] \
                .with_context(**safe_eval(action.context)).create({})
            self.assertEqual(wizard.report_type, expected, xmlid)
            self.assertTrue(wizard.report_type_locked,
                            f"{xmlid} should hide the redundant selector")

    def test_action_print_dispatches_on_report_type(self):
        """action_print must reach the report the user asked for.

        A single Print button serving three reports fails silently if the
        dispatch is wrong -- the wrong statement prints under the right title.
        """
        # These names are load-bearing, not cosmetic: Odoo derives the values
        # model from report_name as 'report.%s' (ir_actions_report.py:1121-1123),
        # so each must equal an existing AbstractModel's _name or the template
        # renders without `wizard`. TestReportsActuallyRender asserts that link
        # directly; this test only checks the dispatch reaches the right one.
        prefix = "account_financial_statements."
        expected_report_name = {
            "balance_sheet": prefix + "balance_sheet",
            "profit_loss": prefix + "profit_loss",
            "cash_flow": prefix + "cash_flow",
        }
        for report_type, report_name in expected_report_name.items():
            wizard = self.env["account.financial.statements.wizard"].create(
                {"report_type": report_type})
            result = wizard.action_print()
            # When the company has never configured its document layout,
            # report_action() nests the real report inside the layout
            # configurator's context. Unwrap that and assert on report_name,
            # which is present in both shapes (the report action carries no id).
            if result.get("type") != "ir.actions.report":
                self.assertEqual(result.get("type"), "ir.actions.act_window",
                                 f"unexpected action for {report_type}: {result}")
                result = result["context"]["report_action"]
            self.assertEqual(result["report_name"], report_name,
                             f"Print sent {report_type} to the wrong report")

    def test_default_is_a_real_statement(self):
        """The combined entry point must open on something printable."""
        wizard = self.env["account.financial.statements.wizard"].create({})
        self.assertIn(wizard.report_type, self.PRESETS.values())
        self.assertFalse(wizard.report_type_locked,
                         "the combined action must leave the selector visible")


@tagged("-at_install", "post_install")
class TestReportsActuallyRender(TransactionCase):
    """Render each statement the way Odoo renders it, not the way we compute it.

    Every other test in this file calls ``_get_report_values`` directly, by model
    name. That proves the arithmetic and proves nothing about the report: Odoo
    never looks the model up that way. It resolves it mechanically as
    ``'report.%s' % report_name`` (``ir_actions_report.py:1121-1123``), and when
    that lookup misses it silently falls back to a context containing only
    ``docs``/``doc_ids``/``doc_model`` -- no ``wizard`` -- so the template dies
    with ``KeyError: 'wizard'``.

    That is exactly what happened: the models were named
    ``report.account_financial_statements.profit_loss`` while the actions asked
    for ``...report_profit_loss_document``. Every unit test passed and not one
    statement could be printed.

    These tests go through ``_render_qweb_html``, which is the only thing that
    would have caught it.
    """

    REPORTS = [
        ("account_financial_statements.action_report_balance_sheet", "Balance Sheet"),
        ("account_financial_statements.action_report_profit_loss", "Profit"),
        ("account_financial_statements.action_report_cash_flow", "Cash Flow"),
    ]

    def _wizard(self):
        return self.env["account.financial.statements.wizard"].create({})

    def test_the_values_model_name_matches_the_report_name(self):
        """The mismatch itself, asserted directly.

        Cheaper to read than a render failure, and it names the rule: the model
        name is not free, it is derived from report_name.
        """
        for xmlid, _label in self.REPORTS:
            with self.subTest(report=xmlid):
                report = self.env.ref(xmlid)
                expected = "report.%s" % report.report_name
                self.assertIsNotNone(
                    self.env.get(expected),
                    f"{xmlid} names report_name={report.report_name!r}, so Odoo will "
                    f"look for the model {expected!r}. That model does not exist, so "
                    f"_get_report_values will never run and the template will render "
                    f"without 'wizard'."
                )

    def test_each_report_renders_from_the_wizard(self):
        """The route a user takes: the wizard button, with data={'wizard_id': id}."""
        wizard = self._wizard()
        for xmlid, marker in self.REPORTS:
            with self.subTest(report=xmlid):
                html, content_type = self.env["ir.actions.report"]._render_qweb_html(
                    xmlid, wizard.ids, data={"wizard_id": wizard.id})
                text = html.decode() if isinstance(html, bytes) else str(html)
                self.assertEqual(content_type, "html")
                self.assertIn(marker, text, f"{xmlid} did not render its own heading")
                # The company name comes from `wizard.company_id`, the expression
                # that raised KeyError. Its presence proves the wizard reached
                # the template.
                self.assertIn(self.env.company.name, text)

    def test_each_report_renders_without_data(self):
        """The route the error page's own retry link takes.

        `/report/html/<report_name>/<id>` arrives with empty `data`, so anything
        reading `data['wizard_id']` unconditionally raises KeyError there even
        after the model name is fixed. The wizard is recovered from docids.
        """
        wizard = self._wizard()
        for xmlid, marker in self.REPORTS:
            with self.subTest(report=xmlid):
                html, _ct = self.env["ir.actions.report"]._render_qweb_html(
                    xmlid, wizard.ids)
                text = html.decode() if isinstance(html, bytes) else str(html)
                self.assertIn(marker, text)

    def test_rendering_without_a_wizard_is_a_clear_error(self):
        """A missing wizard must say so, not raise KeyError from inside QWeb."""
        from odoo.exceptions import UserError  # noqa: PLC0415
        with self.assertRaises(UserError):
            self.env["ir.actions.report"]._render_qweb_html(
                "account_financial_statements.action_report_profit_loss", [])

    def test_the_wizard_buttons_return_a_usable_action(self):
        """The buttons themselves, end to end, including the data payload."""
        wizard = self._wizard()
        for method in ("action_balance_sheet", "action_profit_loss", "action_cash_flow"):
            with self.subTest(method=method):
                action = getattr(wizard, method)()
                self.assertEqual(action.get("type"), "ir.actions.report")
                self.assertEqual(action.get("data", {}).get("wizard_id"), wizard.id,
                                 "the wizard id must reach _get_report_values")
