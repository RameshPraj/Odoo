# -*- coding: utf-8 -*-
"""Each tweak must have the effect it claims, and break nothing reaching it.

Menu assertions go through ``load_menus``, never ``search``: ``ir.ui.menu.search``
applies no group or active filtering of its own for this purpose, so a search-based
test reports menus the client will never draw. That mistake is what let a menu
visibility defect (SEC-12) through a suite written specifically to catch one.
"""
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestDiscussDuplicateHidden(TransactionCase):

    def _delivered(self, user):
        """Every menu name load_menus delivers to this user."""
        menus = self.env["ir.ui.menu"].with_user(user).load_menus(False)
        return [v["name"] for k, v in menus.items() if k != "root"]

    def test_only_one_discuss_menu_is_delivered(self):
        """The point of the tweak: 'Discuss' appears once, not twice."""
        admin = self.env.ref("base.user_admin")
        discusses = [n for n in self._delivered(admin) if n == "Discuss"]
        self.assertEqual(
            len(discusses), 1,
            "stock Odoo delivers two menus named Discuss, the app root and a child "
            "repeating it; local_ui_tweaks should have hidden the child")

    def test_the_duplicate_is_hidden_rather_than_deleted(self):
        """Hidden, so it can be restored by flipping one field.

        Deleting another module's record would make this irreversible without
        reinstalling mail, and would break anything referencing the xmlid.
        """
        dup = self.env.ref("mail.main_menu_discuss")
        self.assertFalse(dup.active)
        self.assertTrue(dup.exists(), "the record must still exist, merely inactive")

    def test_the_discuss_app_still_opens(self):
        """Hiding the child must not leave the app with nowhere to go.

        This is the failure that would matter: the root carries the same action, so
        the tile still works. If a future Odoo moved the action off the root, this
        fails instead of users finding a dead tile.
        """
        root = self.env.ref("mail.menu_root_discuss")
        self.assertTrue(root.active)
        self.assertTrue(root.action, "the Discuss app root has no action to open")
        self.assertIn("Discuss", self._delivered(self.env.ref("base.user_admin")))

    def test_the_rest_of_the_discuss_app_is_untouched(self):
        """Only the duplicate was hidden."""
        delivered = set(self._delivered(self.env.ref("base.user_admin")))
        for name in ("Channels", "Configuration"):
            self.assertIn(name, delivered, f"{name} disappeared from Discuss")
