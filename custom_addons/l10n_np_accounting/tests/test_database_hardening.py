# -*- coding: utf-8 -*-
r"""The database does not hand PUBLIC privileges it should not have (PG-2, PG-4).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_accounting --stop-after-init

PostgreSQL grants two things to ``PUBLIC`` -- every role on the cluster -- that a
tenant database should not:

* **PG-2** ``CONNECT`` on the database, because ``datacl`` is NULL on a fresh
  database and the built-in default then applies.
* **PG-4** ``CREATE`` on ``schema public``. PostgreSQL 15 removed this default and
  **Odoo puts it back**: ``odoo/service/db.py:168-174`` issues
  ``GRANT CREATE ON SCHEMA PUBLIC TO PUBLIC`` on every database it creates.

Both are invisible while a single login role exists, which is exactly why they need
a test rather than a memory. They become real the moment a second role does -- a
reporting user, a metrics exporter, a BI connector -- and nothing about the running
system looks different on the day that happens.

This lives in the test suite rather than in ``lint`` on purpose. QA-1 established
that lint "touches no database and starts no server, so it is safe to run at any
time, including while the server is up", and a database check there would destroy
that property.

Fix a failure with:

    venv\Scripts\python.exe tools\harden_database.py --db <database>

It is idempotent and has to be re-run after every ``createdb``, because Odoo
re-grants PG-4 each time it creates a database.
"""
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestDatabaseHardening(TransactionCase):

    def _privileges(self):
        self.env.cr.execute("""
            SELECT has_database_privilege('public', current_database(), 'CONNECT'),
                   has_schema_privilege('public', 'public', 'CREATE'),
                   current_database()
        """)
        return self.env.cr.fetchone()

    def test_public_cannot_connect_to_this_database(self):
        """PG-2. `datacl` NULL means the default applies: anyone may connect."""
        can_connect, _can_create, database = self._privileges()
        self.assertFalse(
            can_connect,
            f"PUBLIC can CONNECT to {database}, so every role on the cluster can "
            f"reach it. Run: venv\\Scripts\\python.exe tools\\harden_database.py "
            f"--db {database}")

    def test_public_cannot_create_in_schema_public(self):
        """PG-4. Odoo re-grants this on every database it creates."""
        _can_connect, can_create, database = self._privileges()
        self.assertFalse(
            can_create,
            f"PUBLIC can CREATE in schema public on {database}. PostgreSQL 15 "
            f"removed this default; Odoo restores it at createdb time "
            f"(odoo/service/db.py:168-174), so it has to be revoked again after "
            f"each one. Run: venv\\Scripts\\python.exe tools\\harden_database.py "
            f"--db {database}")

    def test_the_owner_kept_the_privileges_it_needs(self):
        """The half that would break the application rather than expose it.

        Revoking from PUBLIC materialises `datacl`, at which point the owner's
        privileges stop being implicit and start being listed. If that had gone
        wrong, Odoo could not connect at all -- so this asserts the *positive*
        side of the same change, not only the negative one.
        """
        self.env.cr.execute("""
            SELECT has_database_privilege(current_user, current_database(), 'CONNECT'),
                   has_schema_privilege(current_user, 'public', 'USAGE'),
                   has_schema_privilege(current_user, 'public', 'CREATE')
        """)
        connect, usage, create = self.env.cr.fetchone()
        self.assertTrue(connect, "the Odoo role must still be able to connect")
        self.assertTrue(usage, "the Odoo role must still be able to use schema public")
        self.assertTrue(create, "the Odoo role must still be able to create tables")
