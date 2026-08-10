# -*- coding: utf-8 -*-
"""Tests that the accounting menus are actually *visible*, not merely present.

These exist because a whole class of bug was missed by checking the wrong thing.
Searching ``ir.ui.menu`` as a given user does NOT apply menu group filtering, so
``Menu.with_user(user).search(...)`` happily returns menus that user can never
see. Only ``load_menus`` applies the group filter. Every assertion here goes
through ``load_menus``.

The specific regression guarded against: in stock Odoo 19 Community,
``group_account_readonly`` and ``group_account_user`` have no ``privilege_id``
and nothing implies them, so the Accounting / Review / Reporting sections are
invisible to every user including the administrator.
"""
from odoo.tests import TransactionCase, tagged

GATED_SECTIONS = ("Accounting", "Review", "Reporting")
ALWAYS_VISIBLE = ("Dashboard", "Customers", "Vendors", "Configuration")


@tagged("-at_install", "post_install")
class TestMenuVisibility(TransactionCase):

    def _visible_sections(self, user):
        """Top-level sections of Accounting Nepal as load_menus would deliver
        them to this user."""
        menus = self.env["ir.ui.menu"].with_user(user).load_menus(False)
        root = menus["root"]
        app = next((menus[child] for child in root["children"]
                    if menus[child]["name"] == "Accounting Nepal"), None)
        self.assertTrue(app, f"the Accounting Nepal app is not delivered to {user.login}")
        return {menus[child]["name"] for child in app["children"]}

    # ---- the group ladder itself -------------------------------------------

    def test_feature_groups_are_selectable(self):
        """Both must sit under the Accounting privilege, or no one can be given
        them from a user form."""
        privilege = self.env.ref("account.res_groups_privilege_accounting")
        for xmlid in ("account.group_account_readonly", "account.group_account_user"):
            group = self.env.ref(xmlid)
            self.assertEqual(group.privilege_id, privilege,
                             f"{xmlid} is not selectable: it has no Accounting privilege")

    def test_administrator_implies_accountant(self):
        """Choosing Administrator must not grant fewer accounting features than
        choosing Accountant."""
        manager = self.env.ref("account.group_account_manager")
        self.assertIn(self.env.ref("account.group_account_user"),
                      manager.all_implied_ids,
                      "Administrator does not imply Accountant")
        self.assertIn(self.env.ref("account.group_account_readonly"),
                      manager.all_implied_ids,
                      "Administrator does not imply Read Only")

    # ---- what users actually see ------------------------------------------

    def test_admin_sees_every_section(self):
        admin = self.env.ref("base.user_admin")
        visible = self._visible_sections(admin)
        missing = set(GATED_SECTIONS + ALWAYS_VISIBLE) - visible
        self.assertFalse(
            missing,
            f"the administrator cannot see {sorted(missing)}. "
            "Check security/account_groups.xml -- this is the exact failure that "
            "hid Accounting, Review and Reporting in stock Community.")

    def test_accountant_sees_the_gated_sections(self):
        user = self.env["res.users"].create({
            "name": "Nepal Accountant", "login": "np_vis_accountant",
            "group_ids": [(6, 0, [self.env.ref("account.group_account_user").id])],
        })
        visible = self._visible_sections(user)
        for section in GATED_SECTIONS:
            self.assertIn(section, visible, f"an Accountant cannot see {section}")

    def test_billing_clerk_does_not_see_the_gated_sections(self):
        """The fix must not hand full accounting to invoicing-only staff."""
        user = self.env["res.users"].create({
            "name": "Nepal Billing Clerk", "login": "np_vis_billing",
            "group_ids": [(6, 0, [self.env.ref("account.group_account_invoice").id])],
        })
        visible = self._visible_sections(user)
        for section in ("Accounting", "Review"):
            self.assertNotIn(section, visible,
                             f"a billing-only user should not see {section}")
        self.assertIn("Customers", visible)

    def test_gated_leaves_are_delivered_not_just_the_parents(self):
        """A visible parent with all children filtered out is still a dead end."""
        admin = self.env.ref("base.user_admin")
        menus = self.env["ir.ui.menu"].with_user(admin).load_menus(False)
        root = menus["root"]
        app = next(menus[c] for c in root["children"]
                   if menus[c]["name"] == "Accounting Nepal")

        delivered = set()

        def walk(node):
            for child in node["children"]:
                delivered.add(menus[child]["name"])
                walk(menus[child])

        walk(app)

        expected = [
            "Journal Entries", "Assets", "Reconcile", "Lock Dates",
            "VAT Returns", "TDS Returns", "Journal Items", "Audit Trail",
            "Balance Sheet", "Profit and Loss", "Cash Flow Statement",
            "Trial Balance", "General Ledger",
            "Partner Ledger", "Aged Receivable", "Aged Payable",
            "Invoice Analysis",
        ]
        missing = [name for name in expected if name not in delivered]
        self.assertFalse(missing, f"not delivered to the administrator: {missing}")

    def test_analytic_menus_follow_the_analytic_setting(self):
        """Analytic Items and Analytic Report are gated on
        `analytic.group_analytic_accounting`, which -- unlike the accounting
        feature groups -- is genuinely reachable: it is the "Analytic
        Accounting" checkbox in Settings. Hidden until then is correct.
        """
        analytic_group = self.env.ref("analytic.group_analytic_accounting")
        user = self.env["res.users"].create({
            "name": "Nepal Analytic Accountant", "login": "np_vis_analytic",
            "group_ids": [(6, 0, [self.env.ref("account.group_account_user").id])],
        })

        def analytic_menus_visible(for_user):
            menus = self.env["ir.ui.menu"].with_user(for_user).load_menus(False)
            root = menus["root"]
            app = next(menus[c] for c in root["children"]
                       if menus[c]["name"] == "Accounting Nepal")
            found = set()

            def walk(node):
                for child in node["children"]:
                    found.add(menus[child]["name"])
                    walk(menus[child])

            walk(app)
            return {"Analytic Items", "Analytic Report"} & found

        self.assertFalse(analytic_menus_visible(user),
                         "analytic menus must stay hidden until the setting is on")

        user.group_ids = [(4, analytic_group.id)]
        self.assertEqual(analytic_menus_visible(user),
                         {"Analytic Items", "Analytic Report"},
                         "enabling Analytic Accounting must reveal both analytic menus")
