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
from odoo.tests import HttpCase, TransactionCase, tagged
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

    # ---- ACC-2: prior years' profit --------------------------------------
    def _balance_sheet(self, **wizard_kwargs):
        wiz = self._wizard(**wizard_kwargs)
        return self.env["report.account_financial_statements.balance_sheet"]._get_report_values(
            None, {"wizard_id": wiz.id})

    def test_balance_sheet_balances_with_a_prior_year_entry(self):
        """ACC-2. This is the test the old one should have been.

        `test_balance_sheet_balances` posts only current-fiscal-year entries, so it
        passed throughout the defect. Assets, liabilities and equity are cumulative
        since inception, but the result added back covered only the current year --
        and Odoo Community posts no year-end closing entry, so prior years' income
        and expense are zeroed nowhere. The sheet came out short by exactly the sum
        of every previous year's profit, and printed a "difference" line on a
        statutory statement.

        The company's fiscal year runs 17 July to 16 July, so 2026-06-01 is the
        previous year for a sheet dated 2026-08-31.
        """
        self._post_expense(50000.0, date="2026-06-01")

        bs = self._balance_sheet()
        self.assertTrue(
            bs["balanced"],
            f"Balance sheet out by {bs['difference']} after a prior-year entry: "
            f"assets={bs['assets']['total']} liab={bs['liabilities']['total']} "
            f"equity={bs['total_equity']} unallocated={bs['unallocated']} "
            f"result={bs['result']}",
        )
        self.assertAlmostEqual(bs["assets"]["total"], bs["total_liab_equity"], places=2)

    def test_the_prior_year_entry_lands_in_unallocated_not_in_the_result(self):
        """Where the figure goes matters as much as that it balances.

        A fix that swept prior years into the Current Period Result would also
        balance, and would misstate this year's profit on the face of the
        statement. Deltas rather than absolutes, because the database holds other
        entries -- the lesson recorded in `test_profit_and_loss_arithmetic` and
        audit finding TST-2.
        """
        before = self._balance_sheet()
        self._post_expense(50000.0, date="2026-06-01")
        after = self._balance_sheet()

        self.assertAlmostEqual(
            after["unallocated"] - before["unallocated"], -50000.0, places=2,
            msg="a prior-year expense must reduce unallocated earnings by its amount")
        self.assertAlmostEqual(
            after["result"] - before["result"], 0.0, places=2,
            msg="a prior-year expense must not move the current period result")

    def test_an_entry_on_the_first_day_of_the_year_is_current_not_prior(self):
        """The `<` versus `<=` boundary in `_unallocated_earnings_domain`.

        `fy['date_from']` is the first day of the current fiscal year, so an entry
        posted on that exact date belongs to this year's result. Off by one and a
        whole day's trading silently becomes history -- invisible to any test whose
        fixtures avoid the boundary, which is why this one sits on it.
        """
        before = self._balance_sheet()
        self._post_expense(7000.0, date="2026-07-17")
        after = self._balance_sheet()

        self.assertAlmostEqual(
            after["result"] - before["result"], -7000.0, places=2,
            msg="an entry on the first day of the fiscal year belongs to this year")
        self.assertAlmostEqual(
            after["unallocated"] - before["unallocated"], 0.0, places=2,
            msg="an entry on the first day of the fiscal year is not a prior year")
        self.assertTrue(after["balanced"])

    def test_the_unallocated_drill_down_ties_to_its_figure(self):
        """A drill-down that disagrees with the figure it hangs off is worse than
        none, because it turns a number you would have trusted into one you cannot.

        The balance sum over the domain is the *negation* of the printed figure,
        exactly as for the Current Period Result -- see `_period_result_domain`.
        """
        self._post_expense(50000.0, date="2026-06-01")
        bs = self._balance_sheet()

        # The domain is already a list of tuples, so it goes straight to search().
        # A `safe_eval(str(...))` round-trip was the first attempt and raises
        # NameError: the domain holds real `datetime.date` objects, which str()
        # renders as `datetime.date(2026, 8, 31)` and safe_eval cannot resolve.
        total = sum(self.env["account.move.line"]
                    .search(bs["unallocated_domain"]).mapped("balance"))
        self.assertAlmostEqual(
            total, -bs["unallocated"], places=2,
            msg="the unallocated-earnings drill-down does not sum to its own figure")

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
        """The four account types the cash-flow statement classifies against.

        Searched first, **created if the chart has none** (TST-3). These used to be
        `search(...)` alone, and all four cash-flow tests began
        `if not all(a.values()): self.skipTest(...)`. Two of those types --
        `asset_fixed` and `liability_non_current` -- are exactly the ones
        `ACCOUNTING_NEPAL.md` records as *missing from this 43-account chart*, so
        the skip was not hypothetical: on this very database the cash-flow suite
        was one chart revision away from silently asserting nothing, and nothing
        printed a skip count to say so.

        Creating them keeps the tests representative where a chart exists and
        honest where it does not.
        """
        A = self.env["account.account"]
        wanted = (
            ("cash", "asset_cash", "TST3CASH", "Test cash"),
            ("income", "income", "TST3INC", "Test income"),
            ("fixed", "asset_fixed", "TST3FIX", "Test fixed asset"),
            ("loan", "liability_non_current", "TST3LOAN", "Test long-term loan"),
        )
        accounts = {}
        for key, account_type, code, name in wanted:
            found = A.search([("account_type", "=", account_type)], limit=1)
            accounts[key] = found or A.create({
                "code": code, "name": name, "account_type": account_type,
                "company_ids": [Command.set([self.env.company.id])],
            })
        return accounts

    def test_cash_flow_reconciles(self):
        """The core guarantee: classified movements must equal the change in cash."""
        a = self._accounts_for_cash_flow()
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

    # ------------------------------------------------------------------
    # Drill-down: every figure must tie to the records its link opens.
    # ------------------------------------------------------------------
    def _sum_over(self, domain):
        groups = self.env["account.move.line"]._read_group(
            domain, groupby=[], aggregates=["balance:sum"])
        return (groups[0][0] or 0.0) if groups else 0.0

    def _assert_ties(self, label, figure, domain, sign):
        """The whole feature rests on this: click a figure, get exactly its lines.

        A drill-down whose total differs from the figure it hangs off is worse
        than no drill-down, because it makes a number you would have trusted look
        wrong. Asserting it per line is what stops that being a convention
        somebody has to remember while editing the report.
        """
        got = sign * self._sum_over(domain)
        self.assertEqual(
            self.company.currency_id.compare_amounts(got, figure), 0,
            f"{label}: the report shows {figure} but its drill-down sums to {got}")

    def _every_figure(self, values, section_keys):
        """Yield (label, figure, domain, sign) for each drillable figure."""
        for key in section_keys:
            section = values[key]
            yield f"{key} total", section["total"], section["domain"], section["sign"]
            for block in section["blocks"]:
                yield (f"{key}/{block['label']} subtotal", block["subtotal"],
                       block["domain"], block["sign"])
                for line in block["lines"]:
                    yield (f"{key}/{line['code']}", line["amount"],
                           line["domain"], line["sign"])

    def test_balance_sheet_drilldowns_tie_to_their_figures(self):
        self._post_invoice(400000.0)
        self._post_expense(120000.0)
        wiz = self._wizard()
        values = self.env[
            "report.account_financial_statements.balance_sheet"
        ]._get_report_values(wiz.ids, {"wizard_id": wiz.id})

        checked = 0
        for label, figure, domain, sign in self._every_figure(
                values, ("assets", "liabilities", "equity")):
            with self.subTest(figure=label):
                self._assert_ties(label, figure, domain, sign)
            checked += 1
        self.assertGreater(checked, 0, "no figures were checked at all")

        # The period-result line spans income and every expense type, so its sum
        # is the negation of the figure. Getting this sign wrong is the single
        # easiest mistake here, hence its own assertion.
        self._assert_ties("result", values["result"],
                          values["result_domain"], values["result_sign"])

    def test_profit_and_loss_drilldowns_tie_to_their_figures(self):
        self._post_invoice(400000.0)
        self._post_expense(120000.0)
        wiz = self._wizard()
        values = self.env[
            "report.account_financial_statements.profit_loss"
        ]._get_report_values(wiz.ids, {"wizard_id": wiz.id})

        for label, figure, domain, sign in self._every_figure(
                values, ("income", "cost_of_sales", "expenses")):
            with self.subTest(figure=label):
                self._assert_ties(label, figure, domain, sign)
        self._assert_ties("net", values["net"],
                          values["net_domain"], values["net_sign"])

    def test_income_drilldown_needs_the_negative_sign(self):
        """Guards the sign specifically, by showing the naive version is wrong.

        Income carries a credit balance, so summing its lines without the sign
        gives the negation. If someone drops `sign` from the line dicts this test
        fails while the totals-only tests would still pass.
        """
        self._post_invoice(400000.0)
        wiz = self._wizard()
        income = self.env[
            "report.account_financial_statements.profit_loss"
        ]._get_report_values(wiz.ids, {"wizard_id": wiz.id})["income"]

        self.assertEqual(income["sign"], -1)
        raw = self._sum_over(income["domain"])
        self.assertEqual(
            self.company.currency_id.compare_amounts(-raw, income["total"]), 0)
        self.assertNotEqual(
            self.company.currency_id.compare_amounts(raw, income["total"]), 0,
            "if the unsigned sum already matched, this test would prove nothing")

    def test_every_line_carries_an_account_id_not_just_a_code(self):
        """Codes are a chart convention and change; ids do not.

        The module docstring says as much, and the drill-down to the account form
        depends on the id being present.
        """
        self._post_invoice(400000.0)
        wiz = self._wizard()
        values = self.env[
            "report.account_financial_statements.balance_sheet"
        ]._get_report_values(wiz.ids, {"wizard_id": wiz.id})
        lines = [line
                 for key in ("assets", "liabilities", "equity")
                 for block in values[key]["blocks"]
                 for line in block["lines"]]
        self.assertTrue(lines, "no lines to check")
        for line in lines:
            self.assertTrue(line["account_id"],
                            f"line {line['code']} carries no account_id")
            self.assertTrue(
                self.env["account.account"].browse(line["account_id"]).exists())

    # ------------------------------------------------------------------
    # Cash flow drills to CONTRIBUTING entries, and must not claim more.
    # ------------------------------------------------------------------
    def test_cash_flow_lines_carry_their_contributing_entries(self):
        a = self._accounts_for_cash_flow()
        self._cash_entry(a["cash"], a["income"], 300000.0, "2026-08-02", "Cash sale")
        wiz = self._wizard()
        cf = self.env["report.account_financial_statements.cash_flow"]._get_report_values(
            wiz.ids, {"wizard_id": wiz.id})

        lines = [line for section in cf["sections"] for line in section["lines"]]
        self.assertTrue(lines, "no movement lines were produced")
        for line in lines:
            self.assertTrue(line["contributor_ids"],
                            f"{line['label']} has no contributing entries")
            self.assertTrue(
                self.env["account.move.line"].browse(
                    line["contributor_ids"]).exists())

    def test_cash_flow_opening_and_closing_do_tie(self):
        """Unlike the movement lines, these two are plain sums."""
        a = self._accounts_for_cash_flow()
        self._cash_entry(a["cash"], a["income"], 300000.0, "2026-08-02", "Cash sale")
        wiz = self._wizard()
        cf = self.env["report.account_financial_statements.cash_flow"]._get_report_values(
            wiz.ids, {"wizard_id": wiz.id})
        self._assert_ties("opening", cf["opening"], cf["opening_domain"], 1)
        self._assert_ties("closing", cf["closing"], cf["closing_domain"], 1)

    # ------------------------------------------------------------------
    # The anomaly panel
    # ------------------------------------------------------------------
    def test_draft_entries_are_reported_when_they_are_counted(self):
        self._post_invoice(400000.0).button_draft()
        wiz = self._wizard()
        wiz.target_move = "all"
        values = self.env[
            "report.account_financial_statements.balance_sheet"
        ]._get_report_values(wiz.ids, {"wizard_id": wiz.id})
        messages = " ".join(str(a["message"]) for a in values["anomalies"])
        self.assertIn("draft", messages.lower(),
                      "a report counting draft entries must say so")

    def test_posted_only_does_not_warn_about_drafts(self):
        self._post_invoice(400000.0).button_draft()
        wiz = self._wizard()          # target_move = 'posted'
        values = self.env[
            "report.account_financial_statements.balance_sheet"
        ]._get_report_values(wiz.ids, {"wizard_id": wiz.id})
        messages = " ".join(str(a["message"]) for a in values["anomalies"])
        self.assertNotIn("draft", messages.lower())

    def test_every_anomaly_is_itself_a_drilldown(self):
        """A warning you cannot act on is only half a warning."""
        self._post_invoice(400000.0)
        wiz = self._wizard()
        wiz.target_move = "all"
        for model in ("balance_sheet", "profit_loss", "cash_flow"):
            values = self.env[
                f"report.account_financial_statements.{model}"
            ]._get_report_values(wiz.ids, {"wizard_id": wiz.id})
            for anomaly in values["anomalies"]:
                with self.subTest(model=model, message=str(anomaly["message"])[:40]):
                    self.assertIn(anomaly["level"],
                                  ("info", "warning", "danger"))
                    self.assertTrue(anomaly["domain"])
                    # It must be a usable domain, not decoration.
                    self.env["account.move.line"].search_count(anomaly["domain"])


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
                expected = f"report.{report.report_name}"
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


@tagged("-at_install", "post_install")
class TestPrintPath(TransactionCase):
    """Printing, which until now did not exist.

    All three statements were `qweb-html` only, so the report viewer's Print
    button had no pdf variant to fire. Each now has a second `ir.actions.report`
    sharing the same `report_name`, which is the whole mechanism -- core looks the
    pdf one up by that name.
    """

    def _wizard(self):
        return self.env["account.financial.statements.wizard"].create({
            "date_from": "2026-07-17", "date_to": "2026-08-31",
        })

    def test_each_statement_has_both_an_html_and_a_pdf_action(self):
        for name in ("balance_sheet", "profit_loss", "cash_flow"):
            with self.subTest(statement=name):
                reports = self.env["ir.actions.report"].search([
                    ("report_name", "=", f"account_financial_statements.{name}"),
                ])
                types = set(reports.mapped("report_type"))
                self.assertEqual(
                    types, {"qweb-html", "qweb-pdf"},
                    "the viewer's Print button looks up the pdf variant by "
                    "report_name; without it printing silently does nothing")

    def test_both_variants_resolve_to_the_same_values_model(self):
        """One template, one values model, two output formats.

        This is what keeps the printout and the screen from drifting: they are not
        two renderings of the same data, they are the same rendering.
        """
        for name in ("balance_sheet", "profit_loss", "cash_flow"):
            for report in self.env["ir.actions.report"].search([
                    ("report_name", "=", f"account_financial_statements.{name}")]):
                with self.subTest(statement=name, type=report.report_type):
                    # assertIsNotNone, not assertTrue: env.get returns an EMPTY
                    # recordset of the model, which is falsy even when the model
                    # exists. assertTrue here fails for a model that is perfectly
                    # fine, which is what it did on the first run.
                    self.assertIsNotNone(
                        self.env.get(f"report.{report.report_name}"),
                        "no AbstractModel matches this report_name")

    def test_the_html_carries_the_drilldown_attributes(self):
        """The attributes ARE the drill-down; no JavaScript can add them later.

        Core wraps [res-id][res-model][view-type] and this project's patch widens
        that to [res-model][domain]. Both read markup produced here, so if these
        attributes stop being emitted the feature disappears with no error.
        """
        wizard = self._wizard()
        html, _ext = self.env["ir.actions.report"]._render_qweb_html(
            "account_financial_statements.action_report_balance_sheet",
            wizard.ids, data={"wizard_id": wizard.id})
        text = html.decode() if isinstance(html, bytes) else str(html)
        self.assertIn('res-model="account.move.line"', text)
        self.assertIn("domain=", text)
        self.assertIn('data-afs-block', text)

    def test_the_pdf_carries_them_too_and_is_therefore_the_same_document(self):
        """Guards the property that made this design worth choosing.

        The drill-down attributes are inert in PDF, so one template can serve both
        outputs. If the PDF ever stopped containing them it would mean the two
        paths had diverged, which is exactly the failure a separate interactive
        component would have invited.
        """
        wizard = self._wizard()
        html, _ext = self.env["ir.actions.report"]._render_qweb_html(
            "account_financial_statements.action_report_balance_sheet",
            wizard.ids, data={"wizard_id": wizard.id})
        text = html.decode() if isinstance(html, bytes) else str(html)
        self.assertIn("data-afs-line", text)
        # And the values model is shared, so the figures cannot differ.
        self.assertEqual(
            self.env.get("report.account_financial_statements.balance_sheet")._name,
            "report.account_financial_statements.balance_sheet")


@tagged("-at_install", "post_install")
class TestPrintPathPdf(HttpCase):
    """Actually invoke wkhtmltopdf, once.

    This is an HttpCase and it has to be. `web.internal_layout` pulls in the
    backend asset bundle, so the rendered HTML references dozens of URLs that
    wkhtmltopdf fetches over HTTP against `web.base.url`. Under a plain
    TransactionCase nothing is listening on that port, so every one of those
    fetches has to time out before the PDF is produced: the first version of this
    test took minutes per statement and logged `Exit with code 1 due to network
    error: ConnectionRefusedError` each time. HttpCase runs a real server, so the
    assets resolve.

    One statement, not three. The engine, the layout and the report_name lookup
    are shared, so a second and third render would re-prove the same mechanism at
    ~seconds each; the per-statement templates are covered by the HTML tests.
    """

    def test_a_statement_renders_a_real_pdf(self):
        wizard = self.env["account.financial.statements.wizard"].create({
            "date_from": "2026-07-17", "date_to": "2026-08-31",
        })
        report = self.env["ir.actions.report"].search([
            ("report_name", "=", "account_financial_statements.balance_sheet"),
            ("report_type", "=", "qweb-pdf"),
        ], limit=1)
        self.assertTrue(report, "no pdf action: the Print button has nothing to fire")

        # force_report_rendering is required. Without it Odoo short-circuits
        # _render_qweb_pdf to _render_qweb_html under the test harness
        # (ir_actions_report.py:1025-1028), so this would pass on a machine with no
        # PDF engine installed at all and prove nothing.
        pdf, ext = report.with_context(
            force_report_rendering=True)._render_qweb_pdf(
                report, wizard.ids, data={"wizard_id": wizard.id})

        self.assertEqual(ext, "pdf")
        self.assertTrue(pdf.startswith(b"%PDF-"), "not a PDF at all")
        self.assertGreater(len(pdf), 3000, "implausibly small for a statement")
