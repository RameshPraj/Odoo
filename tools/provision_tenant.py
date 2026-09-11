#!/usr/bin/env python3
r"""Create a tenant database, closed and proven closed (Phase 3, SAAS-*).

    venv\Scripts\python.exe tools\provision_tenant.py --db odoo19_t_alpha
    venv\Scripts\python.exe tools\provision_tenant.py --db odoo19_t_alpha --dry-run
    ./venv/bin/python3 tools/provision_tenant.py --help

Why this exists, and why it does not use Odoo's own database service
--------------------------------------------------------------------
`odoo/service/db.py:46-53` gates **every mutating** database function behind
`check_db_management_enabled`, which raises `AccessDenied` when `list_db` is
falsy: `exp_create_database`, `exp_duplicate_database`, `exp_drop`, `exp_dump`,
`exp_restore`, `exp_rename`, `exp_change_admin_password`,
`exp_migrate_databases`. This project sets `list_db = False`, correctly -- an
exposed database manager is finding SAAS-6 and was a live cluster-takeover route
(SAAS-2).

So provisioning uses the lower-level primitives instead. That is the better
design rather than a workaround: **the database manager never has to be enabled
to onboard a tenant**, so `list_db = False` stays on permanently instead of being
toggled during onboarding, which is exactly when somebody forgets to toggle it
back.

The three things a fresh tenant needs, and why each is mandatory
---------------------------------------------------------------
**Hardening.** `db.py:170-174` runs `GRANT CREATE ON SCHEMA PUBLIC TO PUBLIC` on
every database it creates -- the comment reads "restore legacy behaviour on
pg15+". A tenant is therefore born *open* every single time, so revoking is part
of creation, not an afterthought. Same statements as `tools/harden_database.py`,
which must also be re-run after any future `createdb` by any other route.

**Secret rotation.** `ir_config_parameter.py:18-25` makes `database.secret` a
per-database uuid4, and `res_users.py:833-844` mints session tokens from it. Two
tenants sharing a secret means **a session minted in one authenticates as the
same uid in the other**. A fresh `_create_empty_database` generates its own, so
rotation is belt-and-braces here -- but it is unconditional, so this tool stays
correct if it is ever changed to clone from a template, which is the obvious
speed optimisation and the exact trap `TESTING.md` warns about.

**Acceptance.** A tenant that cannot be *proven* closed is not provisioned: the
isolation checks run at the end and a failure exits non-zero. `TESTING.md`
specifies test 5 as "a provisioning acceptance test, so a newly created tenant is
proven closed rather than assumed closed".

Exit codes: 0 provisioned and verified, 1 refused or verification failed, 2 could
not run.
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from tenant_boundary import (  # noqa: E402
    BoundaryError,
    assert_tenant,
    load_odoo,
    tenant_argument,
)

#: What a tenant gets installed. `l10n_np_accounting` is the umbrella module, so
#: its `depends` pulls the whole Nepal suite -- listing the members here would be
#: a second, drifting copy of that dependency list.
TENANT_MODULES = ["l10n_np_accounting"]


def database_exists(odoo, name):
    with odoo.sql_db.db_connect("postgres").cursor() as cr:
        cr.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name])
        return bool(cr.fetchone())


def create_database(odoo, name):
    """`_create_empty_database` -- the one creation primitive that is not gated."""
    from odoo.service.db import _create_empty_database

    _create_empty_database(name)


def install_modules(odoo, name, modules):
    """Install through the same path a normal `-i` install uses.

    `install_modules` is an explicit keyword (`orm/registry.py:117-127`), so the
    module list is passed rather than smuggled through `config['init']` -- which
    is how the server does it (`service/server.py:1585`) only because it is
    reading command-line options. `new_db_demo=False`: a tenant must never be
    born holding Odoo's demo records.
    """
    from odoo.modules.registry import Registry

    Registry.new(name, update_module=True, install_modules=modules,
                 new_db_demo=False)


def harden(odoo, name):
    """Revoke what `db.py:170-174` just granted. See tools/harden_database.py."""
    from psycopg2 import sql

    statements = (
        ("PG-2", "REVOKE CONNECT ON DATABASE {db} FROM PUBLIC"),
        ("PG-4", "REVOKE CREATE ON SCHEMA public FROM PUBLIC"),
    )
    with odoo.sql_db.db_connect(name).cursor() as cr:
        for finding, statement in statements:
            rendered = sql.SQL(statement).format(db=sql.Identifier(name))
            print(f"    {finding}  {rendered.as_string(cr._cnx)};")
            cr.execute(rendered)
        cr.commit()


def rotate_secrets(odoo, name):
    """Force a distinct `database.secret` and `database.uuid` for this tenant."""
    from odoo.api import SUPERUSER_ID, Environment
    from odoo.modules.registry import Registry

    registry = Registry(name)
    with registry.cursor() as cr:
        env = Environment(cr, SUPERUSER_ID, {})
        env["ir.config_parameter"].init(force=True)
        cr.commit()
        secret = env["ir.config_parameter"].sudo().get_param("database.secret")
    # Never printed. The whole point of the value is that nobody outside the
    # database knows it; a provisioning log is not a place to put one.
    return bool(secret)


def rollback(odoo, name):
    """Drop a database this run created, after a later step failed."""
    from psycopg2 import sql

    odoo.sql_db.close_db(name)
    with odoo.sql_db.db_connect("postgres").cursor() as cr:
        cr._cnx.autocommit = True
        cr.execute("""
            SELECT pg_terminate_backend(pid) FROM pg_stat_activity
             WHERE datname = %s AND pid <> pg_backend_pid()
        """, [name])
        cr.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(
            sql.Identifier(name)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    tenant_argument(parser, "create")
    parser.add_argument("--modules", default=",".join(TENANT_MODULES),
                        help="comma-separated module list (default: the umbrella "
                             "module, whose depends pull the rest)")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the plan and the guards, change nothing")
    parser.add_argument("--skip-verify", action="store_true",
                        help="provision without running the acceptance checks. "
                             "Deliberately awkward: an unverified tenant is one "
                             "nobody has proven closed")
    args = parser.parse_args()

    try:
        odoo = load_odoo()
    except Exception as exc:  # pragma: no cover - environment problem
        print(f"cannot load Odoo with this project's odoo.conf: {exc}",
              file=sys.stderr)
        return 2

    try:
        name = assert_tenant(args.db, action="create")
    except BoundaryError as exc:
        print(exc, file=sys.stderr)
        return 1

    modules = [m.strip() for m in args.modules.split(",") if m.strip()]

    print("")
    print(f"provisioning {name}")
    print(f"  modules      {', '.join(modules)}")
    print(f"  data_dir     {odoo.tools.config['data_dir']}")

    if args.dry_run:
        print("")
        print("  --dry-run, so nothing was executed. Would:")
        print(f"    1. _create_empty_database({name!r})")
        print(f"    2. install {', '.join(modules)}")
        print("    3. REVOKE CONNECT / REVOKE CREATE  (undo db.py:170-174)")
        print("    4. ir_config_parameter.init(force=True)  (rotate secrets)")
        print("    5. run the isolation acceptance checks")
        return 0

    if database_exists(odoo, name):
        print("")
        print(f"{name} already exists. Refusing to touch it: re-provisioning "
              f"would mean dropping a database that may hold a tenant's data.",
              file=sys.stderr)
        print(f"  To replace it: tools/offboard_tenant.py --db {name} --yes",
              file=sys.stderr)
        return 1

    print("")
    print("  1. creating the database")
    create_database(odoo, name)

    # From here on, failure rolls the database back.
    #
    # The first version of this tool did not, and a wrong Registry.new()
    # signature left a created-but-empty odoo19_t_alpha behind. That is the worst
    # outcome: the next run refuses it as "already exists", so the failure needs
    # manual cleanup before it can even be retried. Dropping is safe here and
    # only here -- the database was created seconds ago by this process and
    # provably holds no tenant data.
    try:
        print(f"  2. installing {', '.join(modules)} (this takes a minute)")
        install_modules(odoo, name, modules)

        print("  3. hardening (undoing the CREATE grant db.py:170-174 just made)")
        harden(odoo, name)

        print("  4. rotating database.secret and database.uuid")
        if not rotate_secrets(odoo, name):
            raise RuntimeError("could not read back a database.secret")
    except BaseException as exc:
        print("")
        print(f"  provisioning failed: {exc}", file=sys.stderr)
        print("  rolling back -- dropping the database this run created",
              file=sys.stderr)
        try:
            rollback(odoo, name)
            print(f"  {name} removed; the cluster is as it was.", file=sys.stderr)
        except Exception as cleanup_exc:
            print(f"  ROLLBACK FAILED: {cleanup_exc}", file=sys.stderr)
            print(f"  {name} exists and is half-provisioned. Remove it with:",
                  file=sys.stderr)
            print(f"    tools/offboard_tenant.py --db {name} --yes --skip-dump",
                  file=sys.stderr)
        return 1

    if args.skip_verify:
        print("")
        print(f"{name} provisioned. NOT verified: --skip-verify was given, so "
              f"nobody has proven this tenant is closed.")
        return 0

    print("  5. verifying isolation")
    from check_tenant_isolation import verify_tenant

    # A fault in the harness must not read as a provisioning failure, nor
    # traceback out of a run that has already created a database. Report it and
    # treat the tenant as unverified, which is what it is.
    try:
        ok = verify_tenant(odoo, name, indent="     ")
    except Exception as exc:
        print("")
        print(f"  the isolation harness itself failed: {exc}", file=sys.stderr)
        print(f"  {name} exists but is UNVERIFIED. Fix the harness, then:",
              file=sys.stderr)
        print(f"    tools/check_tenant_isolation.py --db {name}", file=sys.stderr)
        return 1
    print("")
    if not ok:
        print(f"{name} was created but FAILED its acceptance checks above. It is "
              f"not safe to hand to a tenant. Offboard it, or fix the cause and "
              f"re-run the checks.", file=sys.stderr)
        return 1

    print(f"{name} provisioned and verified closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
