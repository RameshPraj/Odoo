# -*- coding: utf-8 -*-
"""The OCA overlays must actually take effect.

    venv\\Scripts\\python.exe -m odoo -c odoo.conf -d <db> \\
        --test-enable --test-tags /account_reports_interactive --stop-after-init

These assert on the *combined* arch rather than on our own file, because our file
being correct proves nothing: what matters is what Odoo produced after applying
inheritance to the vendored template.
"""
from lxml import etree

from odoo.tests import TransactionCase, tagged

AGED_TEMPLATE = "account_financial_report.report_aged_partner_balance_move_lines"


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
