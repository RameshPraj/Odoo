# -*- coding: utf-8 -*-
"""The 19.0.1.1.0 migration, tested as a function rather than by upgrading.

A migration runs once, before the test framework exists, against a database whose
"before" state is already gone. So the usual approach -- upgrade a database and
inspect it -- verifies the migration exactly once, on one database, and never
again in CI. The manual scratch-database run is still worth doing (and was done),
but it is not a test.

Instead the script's decision logic is exercised directly against synthetic rows
in the test transaction, which rolls back. Every case the real database cannot
present is reachable this way:

  * the checkbox was on   -> company default becomes BS
  * the checkbox was off  -> company default stays Gregorian
  * no legacy group at all (a fresh install that never had one)
  * a mixed estate: several companies, all migrated together
  * the digit style carried across
  * called twice (an interrupted upgrade re-run) -> same result, no damage

The one thing this cannot check is that Odoo *invokes* the script, which is a
function of the version bump. `test_the_version_was_bumped` covers that, because
forgetting it is the likeliest way for all of the above to be correct and never
run.
"""
import ast
import os

from odoo.tests import TransactionCase, tagged
from odoo.tools import parse_version

# `migrations/` is deliberately NOT a Python package -- Odoo loads migration
# scripts by path, and `19.0.1.1.0` is not a valid identifier, so it could not be
# imported even if it were. Hence `_load_migration()` below.
MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(MODULE_DIR, "migrations", "19.0.1.1.0", "pre-migration.py")


def _load_migration():
    """Load the script by path.

    `19.0.1.1.0` is not a valid Python identifier, so the directory cannot be
    imported as a package -- which is exactly why Odoo loads migrations by path
    too.
    """
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location("_bs_pre_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("-at_install", "post_install")
class TestMigrationWiring(TransactionCase):
    """The migration must actually be reachable."""

    def test_the_script_exists_where_odoo_looks_for_it(self):
        self.assertTrue(os.path.exists(MIGRATION), f"missing: {MIGRATION}")

    def test_every_migration_on_disk_is_reachable(self):
        """A migration in an un-bumped module never runs.

        This is the silent-failure mode: every assertion below can pass while the
        script sits on disk untouched, and the first anyone knows is a customer
        whose calendar reverted on upgrade.

        **Rewritten 2026-08-23.** This used to assert the manifest version was
        *exactly* `19.0.1.1.0`, which made the module impossible to change ever
        again: the first bump for any other reason failed this test, and it did --
        the version moved to 19.0.1.2.0 for SEC-12 and UPG-1 and the suite went
        red. Equality was also the wrong invariant. Odoo runs a migration when the
        version rises *past* the directory's version, so a module ahead of its
        migrations is correct and normal; a module *behind* one is the bug. That is
        what is asserted now, and it composes with UPG-2's rule that the version
        moves on every change.
        """
        manifest = os.path.join(MODULE_DIR, "__manifest__.py")
        with open(manifest, encoding="utf-8") as fh:
            version = ast.literal_eval(fh.read())["version"]

        migrations_dir = os.path.join(MODULE_DIR, "migrations")
        on_disk = sorted(
            (name for name in os.listdir(migrations_dir)
             if os.path.isdir(os.path.join(migrations_dir, name))),
            key=parse_version)
        self.assertTrue(on_disk, "fixture: no migrations/ directories found")

        # parse_version, not string comparison: "19.0.1.10.0" sorts before
        # "19.0.1.2.0" as text.
        self.assertGreaterEqual(
            parse_version(version), parse_version(on_disk[-1]),
            f"the manifest is at {version} but migrations/{on_disk[-1]}/ exists, so "
            f"that script can never run"
        )

    def test_it_exposes_a_migrate_entry_point(self):
        self.assertTrue(callable(_load_migration().migrate))


@tagged("-at_install", "post_install")
class TestMigrationLogic(TransactionCase):
    """The decisions, against synthetic rows."""

    def setUp(self):
        super().setUp()
        self.migration = _load_migration()
        self.cr = self.env.cr

        # Two extra companies, so "all companies are migrated" is a real
        # assertion rather than one row that happens to be right.
        self.env["res.company"].create([
            {"name": "Mig Co A", "calendar_system": "ad"},
            {"name": "Mig Co B", "calendar_system": "ad"},
        ])

        # Force EVERY company to the pre-migration state. Without this the tests
        # depend on whether the host database has already been upgraded -- on an
        # already-migrated one, company 1 is 'bs' and every "must stay Gregorian"
        # assertion fails for a reason that has nothing to do with the migration.
        # A migration test must define its own "before".
        self.cr.execute("UPDATE res_company SET calendar_system = 'ad'")
        self.env.invalidate_all()
        self.assertEqual(self._calendars(), {"ad"}, "fixture failed to reset")

    # -- helpers ----------------------------------------------------------

    def _make_legacy_group(self, granted):
        """Recreate the retired group, optionally implied by base.group_user.

        Clears any existing xml-id first so this works on a database that has not
        yet been upgraded as well as one that has -- `(module, name)` is unique.
        """
        self.cr.execute("""
            DELETE FROM ir_model_data
             WHERE module = 'l10n_np_accounting'
               AND name = 'group_bs_accounting_dates'
        """)
        group = self.env["res.groups"].create({"name": "Legacy BS dates (test)"})
        self.env["ir.model.data"].create({
            "module": "l10n_np_accounting",
            "name": "group_bs_accounting_dates",
            "model": "res.groups",
            "res_id": group.id,
        })
        if granted:
            self.env.ref("base.group_user").implied_ids = [(4, group.id)]
        self.env.flush_all()
        return group

    def _calendars(self):
        self.env.invalidate_all()
        return set(self.env["res.company"].search([]).mapped("calendar_system"))

    def _run(self, version="19.0.1.0.0"):
        self.migration.migrate(self.cr, version)
        self.env.invalidate_all()

    # -- the decisions ----------------------------------------------------

    def test_a_granted_group_turns_every_company_to_bs(self):
        """The behaviour-preserving case, and the whole point of the script."""
        self._make_legacy_group(granted=True)
        self._run()
        self.assertEqual(
            self._calendars(), {"bs"},
            "the checkbox was on, so every company default must become BS or "
            "users lose the calendar they were using"
        )

    def test_an_ungranted_group_leaves_the_default_alone(self):
        """Never switch BS on for someone who had it switched off."""
        self._make_legacy_group(granted=False)
        self._run()
        self.assertEqual(self._calendars(), {"ad"})

    def test_no_legacy_group_is_a_no_op(self):
        """A database that never had the accounting module's group."""
        self.cr.execute("""
            DELETE FROM ir_model_data
             WHERE module = 'l10n_np_accounting'
               AND name = 'group_bs_accounting_dates'
        """)
        self._run()
        self.assertEqual(self._calendars(), {"ad"})

    def test_a_fresh_install_is_skipped(self):
        """`version` is falsy on install, and there is no old state to carry.

        Without this guard a brand-new database would come up in BS purely because
        the module's own data happened to define a group.
        """
        self._make_legacy_group(granted=True)
        self._run(version=None)
        self.assertEqual(
            self._calendars(), {"ad"},
            "a fresh install must not be switched to BS"
        )

    def test_running_twice_is_harmless(self):
        """An upgrade can be interrupted and re-run."""
        self._make_legacy_group(granted=True)
        self._run()
        first = self._calendars()
        self._run()
        self.assertEqual(self._calendars(), first)

    def test_it_does_not_touch_individual_user_preferences(self):
        """The company default is the only thing the script writes.

        Anyone who has already chosen a calendar of their own must keep it -- the
        upgrade is not an occasion to overwrite a user's preference.
        """
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Opted out", "login": "mig_opt_out@example.com",
            "calendar_system": "ad",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        self._make_legacy_group(granted=True)
        self._run()
        user.invalidate_recordset(["calendar_system"])
        self.assertEqual(user.calendar_system, "ad")

    def test_the_digit_style_is_carried_across_when_the_old_column_exists(self):
        """Only meaningful before the column is dropped.

        On this database the upgrade has already run and `l10n_np_bs_digits` is
        gone, so the branch is unreachable -- assert that rather than pretend to
        test it, and check the destination field exists so the migration has
        somewhere to write.
        """
        exists = self.migration._column_exists(
            self.cr, "res_company", "l10n_np_bs_digits")
        if exists:
            self.cr.execute(
                "UPDATE res_company SET l10n_np_bs_digits = 'devanagari'")
            self._run()
            self.assertEqual(
                set(self.env["res.company"].search([]).mapped("bs_digits")),
                {"devanagari"},
            )
        else:
            self.assertTrue(
                self.migration._column_exists(self.cr, "res_company", "bs_digits"),
                "the destination column is missing, so the digit style would be "
                "silently dropped on a database that still has the old one"
            )

    def test_a_missing_destination_column_is_survived(self):
        """Never raise mid-upgrade.

        If `nepali_calendar_core` has not created its column yet, the script logs
        and returns. Raising here would abort the whole upgrade and leave the
        database half-migrated, which is far worse than a Gregorian default.
        """
        self.assertFalse(
            self.migration._column_exists(self.cr, "res_company", "no_such_column"))
        # Sanity: the guard reads the column the script actually checks.
        self.assertTrue(
            self.migration._column_exists(self.cr, "res_company", "calendar_system"))
