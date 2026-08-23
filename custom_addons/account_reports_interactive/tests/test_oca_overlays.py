# -*- coding: utf-8 -*-
"""The OCA overlays must actually take effect.

    venv\\Scripts\\python.exe -m odoo -c odoo.conf -d <db> \\
        --test-enable --test-tags /account_reports_interactive --stop-after-init

These assert on the *combined* arch rather than on our own file, because our file
being correct proves nothing: what matters is what Odoo produced after applying
inheritance to the vendored template.
"""
import ast

from lxml import etree
from odoo.tests import TransactionCase, tagged

AGED_TEMPLATE = "account_financial_report.report_aged_partner_balance_move_lines"


def _recpay_accounts(case):
    """The receivable/payable accounts these reports filter on.

    `account_ids` on these wizards has no default and is populated only by onchange,
    which `create()` does not trigger. Omit it and every report renders an empty
    shell — which passes any assertion about *absence* and proves nothing.
    """
    return case.env["account.account"].search([
        ("account_type", "in", ("asset_receivable", "liability_payable")),
        ("company_ids", "in", case.env.company.id),
    ])


def _aged_wizard(case, details=False):
    return case.env["aged.partner.balance.report.wizard"].create({
        "company_id": case.env.company.id,
        "date_at": "2026-08-31",
        "target_move": "posted",
        "account_ids": [(6, 0, _recpay_accounts(case).ids)],
        "show_move_line_details": details,
    })


def _render_via_button(case, wizard):
    """Render the way the web client does, not via a hand-built data dict.

    This distinction is the entire point of these tests. The vendored report's own
    suite builds `data` by hand and so never traversed the wizard that was producing
    a `date_at` of the wrong type — see the module docstring in
    models/aged_partner_balance_wizard.py.
    """
    action = wizard.button_export_html()
    html, _ext = case.env["ir.actions.report"]._render_qweb_html(
        action["report_name"], wizard.ids, data=action["data"])
    return html.decode() if isinstance(html, bytes) else str(html)


def _domains_in(text):
    """Every drill-down domain the rendered HTML carries, parsed."""
    parsed = []
    for raw in etree.HTML(text).xpath("//*[@domain]/@domain"):
        parsed.append(ast.literal_eval(raw))
    return parsed


@tagged("-at_install", "post_install")
class TestAgedPartnerBalanceOverlay(TransactionCase):

    def _arch(self, xmlid):
        return etree.fromstring(self.env.ref(xmlid).get_combined_arch())

    def test_no_raw_domain_attribute_survives(self):
        """A bare `domain=` means QWeb never evaluated the expression.

        Upstream wrote eight of these without the `t-att-` prefix, so the Python
        source text was copied into the HTML attribute verbatim and handed to
        doAction as if it were a domain. The drill-down could not work, and looked
        present in the source, which is why it went unnoticed.
        """
        raw = self._arch(AGED_TEMPLATE).xpath("//span[@domain]")
        self.assertFalse(
            [etree.tostring(node)[:80] for node in raw],
            "a raw domain= attribute is unevaluated Python and cannot drill down")

    def test_all_eight_amounts_became_evaluated_domains(self):
        """Eight, not one.

        The overlay applies the same xpath repeatedly, relying on each application
        removing the attribute it fixed so the next selects the following one. If
        Odoo ever stopped applying inheritance specs sequentially, only the first
        would be fixed -- and everything else would still look fine. Hence the
        exact count.
        """
        evaluated = self._arch(AGED_TEMPLATE).xpath("//span[@t-att-domain]")
        self.assertEqual(len(evaluated), 8)

    def test_the_expressions_still_target_move_lines(self):
        arch = self._arch(AGED_TEMPLATE)
        for node in arch.xpath("//span[@t-att-domain]"):
            self.assertEqual(node.get("res-model"), "account.move.line")
            self.assertIn("line_rec", node.get("t-att-domain"),
                          "the reconciliation expression was lost in the rewrite")

    def test_the_repaired_attributes_survive_a_real_render(self):
        """Arch assertions are not enough: these must reach the HTML evaluated.

        The eight amounts live in the move-line detail template, which renders only
        when `show_move_line_details` is on — so a version of this test without that
        flag passes while exercising none of the fix.
        """
        text = _render_via_button(self, _aged_wizard(self, details=True))
        self.assertNotIn("t-att-domain", text,
                         "t-att-domain reached the output unevaluated")
        domains = _domains_in(text)
        self.assertEqual(len(domains), 8,
                         "expected the eight repaired amounts to emit domains")
        for domain in domains:
            self.env["account.move.line"].search_count(domain)

    def test_the_vendored_file_itself_is_untouched(self):
        """VENDORED.md forbids editing these modules in place.

        The reason is not tidiness: account_financial_report is AGPL-3, and
        modifying it while serving it over a network triggers the publication
        clause. This asserts the fix really is an overlay, by checking the
        original template record still carries the broken markup while the
        combined arch does not.
        """
        original = self.env.ref(AGED_TEMPLATE)
        own_arch = etree.fromstring(original.arch_db)
        self.assertEqual(
            len(own_arch.xpath("//span[@domain]")), 8,
            "the vendored template should still contain its original markup; "
            "if this is 0 somebody edited the AGPL-3 module in place")


@tagged("-at_install", "post_install")
class TestAgedPartnerBalanceRenders(TransactionCase):
    """Aged Partner Balance could not render at all before 2026-08-19.

    Its wizard passed `date_at` as a date while the report did
    `strptime(date_at, ...)`, so every Export raised TypeError. Nobody noticed
    because the report's own tests call `_get_report_values` directly with a
    hand-built string, so they never cross the boundary where the types disagree.
    """

    def test_it_renders_from_its_own_button(self):
        text = _render_via_button(self, _aged_wizard(self))
        self.assertGreater(len(text), 1000)

    def test_the_wizard_is_left_alone(self):
        """The fix must NOT change what the wizard returns.

        Coercing there was the first attempt and it broke two of the vendored
        module's own tests, which convert `date_at` themselves
        (`test_aged_partner_balance.py:63,98`) — the workaround that hid this defect
        in the first place. The coercion belongs at the point of consumption.
        """
        data = _aged_wizard(self)._prepare_report_aged_partner_balance()
        self.assertNotIsInstance(
            data["date_at"], str,
            "the wizard's output changed; upstream tests call .strftime() on it")

    def test_the_report_accepts_either_type(self):
        """Tolerant, like general_ledger.py:793 already is.

        A string must pass through unchanged and a date must be accepted, so this
        keeps working whether or not upstream later fixes the wizard.

        Note `_prepare_report_data`, not `_prepare_report_aged_partner_balance`: the
        latter returns only this report's own keys, and the abstract report needs
        `wizard_name` from the base payload.
        """
        model = self.env["report.account_financial_report.aged_partner_balance"]
        wizard = _aged_wizard(self)
        for date_at in ("2026-08-31", wizard.date_at):
            with self.subTest(supplied=type(date_at).__name__):
                data = dict(wizard._prepare_report_data(), date_at=date_at)
                self.assertTrue(model._get_report_values(wizard.ids, data))

    def test_an_unset_date_from_is_not_turned_into_a_string(self):
        """`date_from` is legitimately unset, and False must stay False.

        Converting unconditionally would make it the string "None", which is truthy,
        so every `if date_from:` downstream would take the wrong branch. That is why
        the override checks each value instead of mapping the whole dict.
        """
        wizard = _aged_wizard(self)
        self.assertFalse(wizard.date_from, "fixture assumption: date_from is unset")
        data = wizard._prepare_report_data()
        self.assertIs(data["date_from"], False)
        # And it survives the override, still False rather than "None".
        self.env["report.account_financial_report.aged_partner_balance"] \
            ._get_report_values(wizard.ids, data)


@tagged("-at_install", "post_install")
class TestDrilldownAddedWhereThereWasNone(TransactionCase):
    """Open Items and Journal Ledger had zero amount-level drill-down.

    Both build their domains from the ids the report already selected rather than
    from a reconstructed filter, because neither figure can be re-derived safely: an
    open-items residual "as at" a past date is a function of reconciliation history,
    not of the current `amount_residual`, and a journal total depends on wizard
    filters that would have to be kept in step by hand.
    """

    def _skip_without_books(self, count):
        if not count:
            self.skipTest("no unreconciled receivable/payable lines to report on")

    def test_open_items_totals_are_drillable(self):
        accounts = _recpay_accounts(self)
        self._skip_without_books(self.env["account.move.line"].search_count([
            ("account_id", "in", accounts.ids), ("parent_state", "=", "posted"),
            ("amount_residual", "!=", 0),
        ]))
        wizard = self.env["open.items.report.wizard"].create({
            "company_id": self.env.company.id,
            "date_at": "2026-08-31",
            "target_move": "posted",
            "hide_account_at_0": False,
            "account_ids": [(6, 0, accounts.ids)],
        })
        text = _render_via_button(self, wizard)
        self.assertNotIn("t-att-domain", text)
        domains = _domains_in(text)
        self.assertTrue(domains, "no ending-balance drill-down was emitted")
        for domain in domains:
            self.env["account.move.line"].search_count(domain)

    def test_journal_ledger_totals_are_drillable(self):
        wizard = self.env["journal.ledger.report.wizard"].create({
            "company_id": self.env.company.id,
            "date_from": "2026-04-01",
            "date_to": "2026-08-31",
            "move_target": "posted",
        })
        text = _render_via_button(self, wizard)
        self.assertNotIn("t-att-domain", text)
        domains = _domains_in(text)
        self.assertTrue(domains, "no journal-total drill-down was emitted")
        for domain in domains:
            self.env["account.move.line"].search_count(domain)

    def test_journal_totals_tie_to_what_they_open(self):
        """The invariant, applied to vendored reports too.

        A journal's debit total must equal the summed debit of the lines its link
        opens. This is the assertion that makes the drill-down trustworthy rather
        than merely present.
        """
        wizard = self.env["journal.ledger.report.wizard"].create({
            "company_id": self.env.company.id,
            "date_from": "2026-04-01",
            "date_to": "2026-08-31",
            "move_target": "posted",
        })
        action = wizard.button_export_html()
        values = self.env[
            "report.account_financial_report.journal_ledger"
        ]._get_report_values(wizard.ids, action["data"])

        checked = 0
        for journal in values["Journal_Ledgers"]:
            ids = [aml["move_line_id"]
                   for move in journal["report_moves"]
                   for aml in move["report_move_lines"]]
            if not ids:
                continue
            for field in ("debit", "credit"):
                groups = self.env["account.move.line"]._read_group(
                    [("id", "in", ids), (field, "!=", 0)],
                    groupby=[], aggregates=[f"{field}:sum"])
                total = (groups[0][0] or 0.0) if groups else 0.0
                self.assertEqual(
                    self.env.company.currency_id.compare_amounts(
                        total, journal[field]), 0,
                    f"journal {journal['name']} shows {field} {journal[field]} "
                    f"but its drill-down sums to {total}")
                checked += 1
        if not checked:
            self.skipTest("no journal activity in the period")
