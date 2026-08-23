# -*- coding: utf-8 -*-
"""Structural tests for the Accounting Nepal menu.

Two failure modes justify these tests:

* A malformed XML file in this module invalidates the merged asset bundle and
  blanks the whole backend, not just this app. That happened four times during
  development, so well-formedness is asserted rather than assumed.
* A menu can point at an action belonging to a module that is not installed.
  The menu then renders and raises only when clicked, which is easy to miss.
"""
import os

from lxml import etree
from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval

MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Items the Enterprise Accounting app has that this app deliberately does not.
# Kept here so the README and the code cannot drift apart silently.
KNOWN_ABSENT = {
    "Deferred Revenues", "Deferred Expenses",
    "Working File", "Annual Report", "Fiscal Report", "Executive Summary",
    "Unrealized Currencies",
}


@tagged("-at_install", "post_install")
class TestMenuIntegrity(TransactionCase):

    def _root(self):
        menu = self.env["ir.ui.menu"].search(
            [("parent_id", "=", False), ("name", "=", "Accounting Nepal")], limit=1)
        self.assertTrue(menu, "the Accounting Nepal root menu is missing")
        return menu

    def _descendants(self, menu):
        children = self.env["ir.ui.menu"].search([("parent_id", "=", menu.id)])
        found = children
        for child in children:
            found |= self._descendants(child)
        return found

    def test_every_xml_file_is_well_formed(self):
        """A double hyphen inside an XML comment blanks the entire backend.

        Parsed with lxml, which is what Odoo itself uses in
        ``tools/convert.py``. minidom is deliberately not used here: it accepts
        a double hyphen inside a comment, so it silently passes the exact defect
        this test exists to catch.
        """
        checked = 0
        for folder, _dirs, files in os.walk(MODULE_ROOT):
            for name in files:
                if not name.endswith(".xml"):
                    continue
                path = os.path.join(folder, name)
                try:
                    etree.parse(path)
                except etree.XMLSyntaxError as error:
                    self.fail(f"{path} is not well-formed XML: {error}")
                checked += 1
        self.assertTrue(checked, "no XML files found; is the test looking in the right place?")

    def test_every_menu_action_resolves(self):
        broken = []
        for menu in self._descendants(self._root()):
            if not menu.action:
                continue
            try:
                menu.action.read(["name"])
            except Exception as error:  # noqa: BLE001
                broken.append(f"{menu.complete_name}: {error}")
        self.assertFalse(broken, "menu items point at unusable actions:\n" + "\n".join(broken))

    def test_act_window_domains_and_contexts_evaluate(self):
        """A domain that only fails at click time is worse than one that fails here."""
        broken = []
        for menu in self._descendants(self._root()):
            action = menu.action
            if not action or action._name != "ir.actions.act_window":
                continue
            for attribute in ("domain", "context"):
                expression = action[attribute]
                if not expression:
                    continue
                try:
                    safe_eval(expression, {"uid": self.env.uid, "context_today": lambda: None})
                except Exception as error:  # noqa: BLE001
                    broken.append(f"{menu.complete_name} {attribute}: {error}")
        self.assertFalse(broken, "unevaluable menu actions:\n" + "\n".join(broken))

    def test_statements_are_three_separate_items(self):
        """Balance Sheet, Profit and Loss and Cash Flow are three reports in
        Enterprise and must be three menu items here, not one combined entry."""
        names = set(self._descendants(self._root()).mapped("name"))
        for expected in ("Balance Sheet", "Profit and Loss", "Cash Flow Statement"):
            self.assertIn(expected, names)

    def test_aged_reports_are_two_separate_items(self):
        names = set(self._descendants(self._root()).mapped("name"))
        self.assertIn("Aged Receivable", names)
        self.assertIn("Aged Payable", names)

    def test_closing_section_is_complete(self):
        names = set(self._descendants(self._root()).mapped("name"))
        for expected in ("Reconcile", "Lock Dates", "VAT Returns", "TDS Returns"):
            self.assertIn(expected, names)

    def test_assets_and_liabilities_holds_registers_only(self):
        """In Enterprise this section lists asset and liability *records*
        (Assets, Loans). Actions performed on them, such as the batch
        depreciation wizard, belong under Closing. Keeping a wizard here made
        the section look complete when the Loans register was in fact missing.
        """
        section = self.env.ref("l10n_np_accounting.menu_np_acc_assets_liab")
        children = set(self._descendants(section).mapped("name"))
        self.assertEqual(children, {"Assets", "Loans"},
                         "this section holds registers only; actions belong elsewhere")

    def test_known_absent_items_are_still_absent(self):
        """If one of these is ever implemented, this test fails and the README
        must be updated in the same commit."""
        names = set(self._descendants(self._root()).mapped("name"))
        now_present = KNOWN_ABSENT & names
        self.assertFalse(
            now_present,
            f"{sorted(now_present)} now exist -- remove them from KNOWN_ABSENT here "
            "and from the 'Genuinely missing' table in README.md")

    def test_no_menu_item_is_an_empty_group(self):
        """A parent with neither an action nor visible children is dead furniture."""
        empty = []
        for menu in self._descendants(self._root()):
            if menu.action:
                continue
            if not self.env["ir.ui.menu"].search_count([("parent_id", "=", menu.id)]):
                empty.append(menu.complete_name)
        self.assertFalse(empty, "menu groups with no children:\n" + "\n".join(empty))
