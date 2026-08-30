#!/usr/bin/env python3
r"""Revoke PUBLIC's default privileges on an Odoo database (PG-2, PG-4).

    venv\Scripts\python.exe tools\harden_database.py --db odoo19
    venv\Scripts\python.exe tools\harden_database.py --db odoo19 --dry-run
    ./venv/bin/python3 tools/harden_database.py --help

Why this exists
---------------
PostgreSQL hands two privileges to ``PUBLIC`` — every role on the cluster — that a
tenant database should not grant:

* **PG-2** ``CONNECT`` on the database. ``datacl`` is NULL on a fresh database,
  which means the built-in default applies: anyone may connect.
* **PG-4** ``CREATE`` on ``schema public``. PostgreSQL 15 removed this default, and
  **Odoo puts it back**: ``odoo/service/db.py:168-174`` issues
  ``GRANT CREATE ON SCHEMA PUBLIC TO PUBLIC`` on every database it creates.

Both are latent while one login role exists and become real the moment a second one
does — a reporting user, a metrics exporter, a BI connector. That is why the fix
belongs in provisioning rather than in a one-off: PG-4 in particular is re-granted
by Odoo every time a database is created, so this script is what runs *after*
``createdb``, not once ever.

Scope guard
-----------
This cluster is shared with another team's database. The script therefore refuses
any database whose name does not begin with ``odoo``, and refuses the maintenance
databases outright. That is belt and braces rather than the real protection: the
``odoo`` role is not a superuser and owns only its own databases, so PostgreSQL
would itself reject these statements against anything else. The guard exists so the
*intent* is visible in the source, not just enforced at the far end.

``template1`` is deliberately **not** hardened. Doing so is the usual advice and is
wrong here: a template change is cluster-wide and would silently alter what every
other team's new databases look like.

Idempotent: ``REVOKE`` of a privilege that is already absent is a no-op, so this can
run after every provision without a guard.

Exit codes: 0 hardened (or already hardened), 1 refused or failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

#: Databases this script will act on. Anything else is refused -- see "Scope guard".
ALLOWED_DB = re.compile(r"^odoo[0-9_a-z-]*$", re.I)
REFUSED_OUTRIGHT = {"postgres", "template0", "template1"}

STATEMENTS = (
    ("PG-2", "REVOKE CONNECT ON DATABASE {db} FROM PUBLIC"),
    ("PG-4", "REVOKE CREATE ON SCHEMA public FROM PUBLIC"),
)

INSPECT = """
    SELECT
        (SELECT datacl::text FROM pg_database WHERE datname = current_database()),
        (SELECT nspacl::text FROM pg_namespace WHERE nspname = 'public'),
        has_database_privilege('public', current_database(), 'CONNECT'),
        has_schema_privilege('public', 'public', 'CREATE')
"""


def inspect(cr):
    cr.execute(INSPECT)
    datacl, nspacl, can_connect, can_create = cr.fetchone()
    return {
        "datacl": datacl,
        "nspacl": nspacl,
        "public_can_connect": can_connect,
        "public_can_create": can_create,
    }


def report(label, state):
    print(f"  {label}")
    print(f"    datacl            {state['datacl']}")
    print(f"    schema public acl {state['nspacl']}")
    print(f"    PUBLIC CONNECT    {state['public_can_connect']}")
    print(f"    PUBLIC CREATE     {state['public_can_create']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True,
                        help="database to harden; never defaulted, because a "
                             "destructive-sounding default on a shared cluster is "
                             "how the wrong database gets touched")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the ACLs and the statements, change nothing")
    args = parser.parse_args()

    name = args.db
    if name in REFUSED_OUTRIGHT or not ALLOWED_DB.match(name):
        print(f"refusing to touch {name!r}: this script acts only on databases "
              f"named odoo*, because the cluster is shared with another team.",
              file=sys.stderr)
        return 1

    try:
        import odoo
        from odoo.tools import config
        config.parse_config(["-c", str(REPO / "odoo.conf")])
        odoo.sql_db  # noqa: B018 -- imported for its side effect of pool setup
        from odoo.sql_db import db_connect
    except Exception as exc:  # pragma: no cover - environment problem
        print(f"cannot load Odoo to reuse odoo.conf's credentials: {exc}",
              file=sys.stderr)
        return 2

    from psycopg2 import sql

    connection = db_connect(name)
    with connection.cursor() as cr:
        before = inspect(cr)
        print("")
        print(f"{name}: PUBLIC privileges before")
        report("", before)

        if args.dry_run:
            print("")
            print("  --dry-run, so nothing was executed. Would run:")
            for finding, statement in STATEMENTS:
                print(f"    {finding}  {statement.format(db=name)};")
            return 0

        print("")
        for finding, statement in STATEMENTS:
            rendered = sql.SQL(statement).format(db=sql.Identifier(name))
            print(f"  {finding}  {rendered.as_string(cr._cnx)};")
            cr.execute(rendered)
        cr.commit()

        after = inspect(cr)
        print("")
        print(f"{name}: PUBLIC privileges after")
        report("", after)

    if after["public_can_connect"] or after["public_can_create"]:
        print("")
        print("PUBLIC still holds a privilege after the revoke. That usually means "
              "the role running this does not own the database or the schema.",
              file=sys.stderr)
        return 1

    print("")
    print(f"{name} hardened: PUBLIC can neither connect to the database nor create "
          f"in schema public.")
    print("Re-run this after every createdb -- Odoo re-grants CREATE on schema "
          "public each time it creates a database (odoo/service/db.py:168-174).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
