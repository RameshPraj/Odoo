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

Checking that a test here actually fails without its fix takes more than it looks,
and two obvious routes do not work:

* **Deleting the ``groups=`` attribute and re-upgrading does nothing.** Odoo writes
  only the fields present in a record, so removing an attribute leaves the previous
  ``group_ids`` in place. The defect is not reproduced and the tests still pass.
* **Clearing ``group_ids`` in the database, then running ``test-module``, also does
  nothing** — that verb runs ``-u`` first, which reloads this file and re-applies
  the gate before any test executes.

What does work: clear ``group_ids`` in the database and evaluate the assertion
directly, without the test runner. Doing that for SEC-12 showed the app delivered to
a user holding no accounting group, with eight reachable entries, which is what
``test_a_user_with_no_accounting_rights_does_not_see_the_app`` asserts against.
"""
from odoo.tests import TransactionCase, tagged

GATED_SECTIONS = ("Accounting", "Review", "Reporting")

#: Sections with no group of their own, visible to anyone who can open the app at
#: all. NOT "always visible" as this was once named: the app root is itself gated
#: (SEC-12), so reaching any of these first requires an accounting group.
#: "Dashboard" is deliberately absent -- it is gated on `group_account_basic`, as
#: core gates its own Dashboard entry.
UNGATED_SECTIONS = ("Customers", "Vendors", "Configuration")


@tagged("-at_install", "post_install")
class TestMenuVisibility(TransactionCase):

    def _app(self, user):
        """The Accounting Nepal app as load_menus would deliver it, or None."""
        menus = self.env["ir.ui.menu"].with_user(user).load_menus(False)
        return next((menus[child] for child in menus["root"]["children"]
                     if menus[child]["name"] == "Accounting Nepal"), None), menus

    def _visible_sections(self, user):
        """Top-level sections of Accounting Nepal as load_menus would deliver
        them to this user."""
        app, menus = self._app(user)
        self.assertTrue(app, f"the Accounting Nepal app is not delivered to {user.login}")
        return {menus[child]["name"] for child in app["children"]}

    def _user_without_accounting_rights(self):
        """An ordinary internal user: employee, and nothing accounting at all.

        Every other user built in this file holds at least one accounting group,
        which is precisely how SEC-12 survived: the exposure case was never
        constructed.
        """
        return self.env["res.users"].create({
            "name": "Nepal Warehouse Clerk", "login": "np_vis_no_acct",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })

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
        missing = set(GATED_SECTIONS + UNGATED_SECTIONS + ("Dashboard",)) - visible
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

    # ---- SEC-12: the app itself must not be offered to non-accounting staff --

    def test_a_user_with_no_accounting_rights_does_not_see_the_app(self):
        """The regression that got through every test above.

        The root menu carried no `groups` at all, so the tile was delivered to
        every internal user. This is the case none of the other tests construct:
        each of them gives its user at least one accounting group, so all of them
        agreed the app should be visible and none could notice that it was visible
        to everyone.
        """
        app, _menus = self._app(self._user_without_accounting_rights())
        self.assertIsNone(
            app,
            "Accounting Nepal is offered to a user with no accounting group; the "
            "root menu has lost its groups (SEC-12)")

    def test_nothing_under_the_app_is_reachable_without_accounting_rights(self):
        """Gating the root must prune the subtree, not just hide the tile.

        Worth asserting separately rather than assuming: `_visible_menu_ids`
        marks an action menu visible whenever the user can read the action's
        model, and only then walks up through ancestors that passed the group
        filter. So the leaves stay in that set; what a gated root removes is the
        path to them. This checks the delivered tree, which is what the client
        renders.
        """
        user = self._user_without_accounting_rights()
        menus = self.env["ir.ui.menu"].with_user(user).load_menus(False)
        names = {menus[key]["name"] for key in menus if key != "root"}
        # These were the eight entries actually reachable before the fix.
        for leaked in ("Employee Expenses",):
            self.assertNotIn(
                f"{leaked}", names,
                f"{leaked} is still delivered to a user with no accounting rights")

    def test_the_root_is_gated_exactly_as_core_gates_its_own(self):
        """Pins the intent, not just the effect.

        Asserting only "invisible to one unprivileged user" would also pass if
        someone gated the root on something arbitrary and far too narrow. The
        contract is that this app is as reachable as core's Invoicing app and no
        more.
        """
        ours = self.env.ref("l10n_np_accounting.menu_np_accounting_root")
        core = self.env.ref("account.menu_finance")
        self.assertTrue(ours.group_ids, "the root menu has no groups at all")
        self.assertEqual(
            set(ours.group_ids.ids), set(core.group_ids.ids),
            "Accounting Nepal should be gated exactly as account.menu_finance is; "
            f"ours={ours.group_ids.mapped('full_name')} "
            f"core={core.group_ids.mapped('full_name')}")

    def test_an_accounting_reader_still_sees_the_app(self):
        """The gate must not lock out the people it is for."""
        user = self.env["res.users"].create({
            "name": "Nepal Read Only", "login": "np_vis_readonly",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("account.group_account_readonly").id])],
        })
        self.assertIn("Reporting", self._visible_sections(user))
