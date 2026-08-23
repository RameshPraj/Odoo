# -*- coding: utf-8 -*-
r"""The accounting permission ladder this module completes stays completed (UPG-1).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_accounting --stop-after-init

``security/account_groups.xml`` writes to three ``res.groups`` records **owned by
the `account` module**: it gives ``group_account_readonly`` and
``group_account_user`` the accounting privilege so they can be selected on a user
form, renames them, and makes ``group_account_manager`` imply
``group_account_user``. Without that, a stock Community database has nobody who
can see the Accounting, Review and Reporting menus -- not even the administrator.

UPG-1 warned that any ``-u account`` would reload those records from upstream XML
and silently undo all of it. **Measured on a probe database, that does not
happen**, and the reason is structural: ``-u`` propagates to every module that
depends on the named one, and dependents always load after their dependencies.
``-u account`` therefore reloads ``account`` (64/153) *and*
``l10n_np_accounting`` (119/153) in the same transaction, so this module's XML
re-applies the values immediately after upstream resets them. Three consecutive
``-u account`` runs left ``name``, ``privilege_id``, ``sequence`` and
``implied_ids`` byte-identical.

Two further details narrow the original claim. Upstream declares only ``name`` and
``implied_ids`` on these records, so ``privilege_id``, ``sequence`` and ``comment``
were never at risk. And upstream's ``implied_ids`` uses ``(4, ref(...))``, which
links rather than replaces, so the manager-implies-accountant edge would have
survived a reload even on its own.

**The prescribed fix was therefore not applied**, and this test exists instead.
UPG-1 proposed moving the wiring to an idempotent ``post_init_hook``. That would be
strictly worse here: a ``post_init_hook`` runs on **install only**, so it would not
re-run during ``-u account`` -- it would introduce exactly the fragility the
current arrangement avoids by accident of dependency ordering.

What remains valid in UPG-1 is the design objection, which no test can fix: these
are records owned by another module, so uninstalling this one leaves them changed.
``account_groups.xml`` says so in its own header.

This test is the guard. It asserts the invariant rather than the mechanism, so if a
future Odoo release changes how reloads or dependency propagation work, the suite
says so instead of a user discovering that the Accounting menu has gone.
"""
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestAccountGroupWiring(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.readonly = cls.env.ref("account.group_account_readonly")
        cls.accountant = cls.env.ref("account.group_account_user")
        cls.manager = cls.env.ref("account.group_account_manager")
        cls.privilege = cls.env.ref("account.res_groups_privilege_accounting")

    def test_both_groups_are_selectable_on_a_user_form(self):
        """Without a privilege a group has no widget to be chosen from, so it can
        exist and still be unassignable. That was the original defect."""
        for group in (self.readonly, self.accountant):
            with self.subTest(group=group.name):
                self.assertEqual(
                    group.privilege_id, self.privilege,
                    f"{group.name} has no accounting privilege, so nobody can be "
                    f"given it from a user form")

    def test_administrator_is_a_superset_of_accountant(self):
        """Otherwise picking "Administrator" grants *fewer* accounting features
        than picking "Accountant", which is a trap rather than a hierarchy."""
        self.assertIn(self.accountant, self.manager.implied_ids,
                      "group_account_manager no longer implies group_account_user")

    def test_the_ladder_is_transitively_complete(self):
        """An administrator must end up holding the read-only group too, since the
        Accounting and Reporting menus are gated on it."""
        self.assertIn(self.readonly, self.manager.all_implied_ids,
                      "an administrator does not hold group_account_readonly, so "
                      "the Accounting and Reporting menus are invisible to them")

    def test_the_groups_carry_their_intended_names(self):
        """`name` is the one field upstream also declares, so it is the only one a
        reload could plausibly revert. Asserted so a revert is visible here rather
        than in the user interface."""
        self.assertEqual(self.readonly.name, "Accounting - Read Only")
        self.assertEqual(self.accountant.name, "Accountant")

    def test_an_administrator_user_can_reach_the_accounting_menus(self):
        """The end-to-end statement of the same thing, through the only API that
        applies group filtering. A `search()` on `ir.ui.menu` does not filter by
        groups and would pass regardless -- recorded in TESTING.md after that
        mistake was made here."""
        user = self.env["res.users"].create({
            "name": "UPG-1 admin", "login": "upg1_admin",
            "group_ids": [(6, 0, [self.manager.id])],
        })
        visible = self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()
        reachable = self.env["ir.ui.menu"].browse(sorted(visible)).filtered(
            lambda m: m.name in ("Accounting", "Reporting"))
        self.assertTrue(
            reachable,
            "an account manager can see neither Accounting nor Reporting")
