#!/usr/bin/env python3
r"""Cross-tenant isolation checks, from the specification in TESTING.md:185-288.

    venv\Scripts\python.exe tools\check_tenant_isolation.py --db odoo19_t_alpha
    venv\Scripts\python.exe tools\check_tenant_isolation.py --db odoo19_t_alpha \
        --against odoo19_t_beta
    ./venv/bin/python3 tools/check_tenant_isolation.py --help

`TESTING.md` specifies nine tests and says of them: *"None of these exist. They
are the deliverable that proves tenant A can never reach tenant B, and they
should be written **before** the SaaS pivot, not after."*

This implements the ones assertable without a live server and DNS, and **reports
the rest as gaps rather than pretending to cover them**. A stub that passes
because it asserts nothing is worse than a blank: it converts an unknown into a
false assurance, which is the failure mode this project has hit repeatedly
(TST-1, TST-3, TST-9).

Three outcomes, because the specification expects one of them to fail
---------------------------------------------------------------------
* **PASS** -- asserted and holds.
* **FAIL** -- asserted and broken. Exits non-zero.
* **GAP** -- asserted, known broken, and recorded as a finding rather than
  treated as a regression. `TESTING.md` says of test 9's second half: *"will fail
  today (SAAS-8: one global pool) -- which is precisely the point of writing
  it."* A harness that cannot express "broken on purpose, tracked" would force
  that check to be deleted or to lie.

What is NOT covered here, and why
---------------------------------
The HTTP halves of tests 1, 2 and 3, and all of test 7, need a **running server
with `dbfilter` set and two hostnames resolving to it** -- an nginx plus
hosts-file harness that is its own piece of work, and the next step after the
routing layer exists. Test 9's latency half needs load generation. Each is listed
in the summary as DEFERRED with its reason, so the coverage gap is visible in the
output rather than buried here.

Exit codes: 0 all PASS (GAPs allowed), 1 a FAIL, 2 could not run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tenant_boundary import (  # noqa: E402
    BoundaryError,
    assert_tenant,
    filestore_path,
    load_odoo,
)

PASS, FAIL, GAP = "PASS", "FAIL", "GAP"


class Results:
    def __init__(self, indent=""):
        self.rows = []
        self.indent = indent

    def record(self, outcome, spec, label, detail=""):
        self.rows.append((outcome, spec, label, detail))
        mark = {PASS: "ok  ", FAIL: "FAIL", GAP: "gap "}[outcome]
        print(f"{self.indent}{mark} [{spec}] {label}")
        if detail:
            print(f"{self.indent}       {detail}")

    @property
    def failed(self):
        return [r for r in self.rows if r[0] == FAIL]

    @property
    def gaps(self):
        return [r for r in self.rows if r[0] == GAP]


def _param(odoo, db, key):
    """Read one ir.config_parameter without going through a registry.

    Deliberately SQL: building a registry for another tenant would load its
    modules into this process, and the point of these checks is to touch the
    other tenant as little as possible.
    """
    with odoo.sql_db.db_connect(db).cursor() as cr:
        cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", [key])
        row = cr.fetchone()
        return row[0] if row else None


# ---------------------------------------------------------------------------
# spec 5 -- PostgreSQL-level isolation. Specified as a provisioning acceptance
# test, so it runs on every provision.
# ---------------------------------------------------------------------------
def check_postgres_isolation(odoo, db, results):
    with odoo.sql_db.db_connect(db).cursor() as cr:
        cr.execute("""
            SELECT has_database_privilege('public', current_database(), 'CONNECT'),
                   has_schema_privilege('public', 'public', 'CREATE')
        """)
        can_connect, can_create = cr.fetchone()
        results.record(
            FAIL if can_connect else PASS, "5",
            "PUBLIC cannot CONNECT to the tenant database",
            "run tools/harden_database.py --db " + db if can_connect else "")
        results.record(
            FAIL if can_create else PASS, "5",
            "PUBLIC cannot CREATE in schema public",
            "db.py:170-174 re-grants this on every create" if can_create else "")

        cr.execute("""
            SELECT extname FROM pg_extension
             WHERE extname IN ('dblink', 'postgres_fdw')
        """)
        bridges = [r[0] for r in cr.fetchall()]
        results.record(
            FAIL if bridges else PASS, "5",
            "no cross-database bridge extension is installed",
            f"found: {', '.join(bridges)}" if bridges else "")

        cr.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        is_super = cr.fetchone()[0]
        results.record(
            FAIL if is_super else PASS, "5",
            "the Odoo role is not a superuser",
            "a superuser bypasses every grant above" if is_super else "")

        # The owner must keep what the application needs. Asserted because
        # revoking from PUBLIC materialises datacl, at which point the owner's
        # privileges stop being implicit -- if that went wrong, Odoo could not
        # connect at all, and this is the check that would say so.
        cr.execute("""
            SELECT has_database_privilege(current_user, current_database(), 'CONNECT'),
                   has_schema_privilege(current_user, 'public', 'CREATE')
        """)
        owner_connect, owner_create = cr.fetchone()
        results.record(
            PASS if (owner_connect and owner_create) else FAIL, "5",
            "the Odoo role kept CONNECT and CREATE",
            "" if (owner_connect and owner_create) else "the tenant is unusable")


# ---------------------------------------------------------------------------
# spec 1 -- the primitive everything else leans on.
# ---------------------------------------------------------------------------
def check_secret_is_distinct(odoo, db, other, results):
    mine = _param(odoo, db, "database.secret")
    if not mine:
        results.record(FAIL, "1", "the tenant has a database.secret",
                       "sessions cannot be signed without one")
        return
    results.record(PASS, "1", "the tenant has its own database.secret")

    if not other:
        results.record(
            GAP, "1", "database.secret differs from another tenant's",
            "no second tenant given; pass --against <db> to assert this. It is "
            "the assertion a template-clone provisioning bug would break")
        return

    theirs = _param(odoo, other, "database.secret")
    same = bool(theirs) and mine == theirs
    results.record(
        FAIL if same else PASS, "1",
        f"database.secret differs from {other}",
        "IDENTICAL -- a session minted in one tenant will authenticate as the "
        "same uid in the other. Almost certainly a CREATE DATABASE ... TEMPLATE "
        "without ir_config_parameter.init(force=True)" if same else "")

    mine_uuid = _param(odoo, db, "database.uuid")
    theirs_uuid = _param(odoo, other, "database.uuid")
    results.record(
        FAIL if (mine_uuid and mine_uuid == theirs_uuid) else PASS, "1",
        f"database.uuid differs from {other}")


# ---------------------------------------------------------------------------
# spec 3 -- filestore containment (the parts that need no HTTP).
# ---------------------------------------------------------------------------
def check_filestore_containment(odoo, db, other, results):
    mine = filestore_path(db).resolve()
    results.record(
        PASS if mine.name == db else FAIL, "3",
        "the tenant's filestore is keyed by database name",
        f"expected .../filestore/{db}, got {mine}" if mine.name != db else "")

    if other:
        theirs = filestore_path(other).resolve()
        overlap = mine == theirs or mine in theirs.parents or theirs in mine.parents
        results.record(
            FAIL if overlap else PASS, "3",
            f"the filestore does not overlap {other}'s")

    # `_full_path` must strip traversal out of a stored filename. Asserted
    # against the real implementation rather than reimplemented here.
    from odoo.api import SUPERUSER_ID, Environment
    from odoo.modules.registry import Registry

    registry = Registry(db)
    with registry.cursor() as cr:
        env = Environment(cr, SUPERUSER_ID, {})
        attachment = env["ir.attachment"].sudo()
        escaped = None
        for candidate in ("../../../../etc/passwd", "..\\..\\..\\evil", "a/../../b"):
            try:
                resolved = Path(attachment._full_path(candidate)).resolve()
            except Exception:  # noqa: S112 - refusing outright IS containment
                continue
            if mine not in resolved.parents and resolved != mine:
                escaped = (candidate, resolved)
                break
        results.record(
            FAIL if escaped else PASS, "3",
            "a traversal in a stored filename cannot escape the filestore",
            f"{escaped[0]!r} resolved to {escaped[1]}" if escaped else "")


# ---------------------------------------------------------------------------
# spec 4 -- the database manager. The live cluster-takeover regression test.
# ---------------------------------------------------------------------------
def check_database_manager_closed(odoo, results):
    from odoo.tools import config

    results.record(
        FAIL if config["list_db"] else PASS, "4",
        "list_db is off, so every mutating db route is blocked",
        "db.py:46-53 gates them on this flag" if config["list_db"] else "")

    # A method on `config`, not a module function -- the web controller calls it
    # as `odoo.tools.config.verify_admin_password('admin')`
    # (web/controllers/database.py:32).
    weak = config.verify_admin_password("admin")
    results.record(
        FAIL if weak else PASS, "4",
        "the master password is not the default 'admin'",
        "one unauthenticated POST claims the cluster (SAAS-2)" if weak else "")

    stored = config.get("admin_passwd") or ""
    results.record(
        PASS if stored.startswith("$") else GAP, "4",
        "the master password is stored hashed",
        "" if stored.startswith("$") else "plaintext in odoo.conf")


# ---------------------------------------------------------------------------
# spec 6 -- cron fan-out. Static, because the dynamic half needs a live sweep.
# ---------------------------------------------------------------------------
def check_cron_scope(odoo, results):
    from odoo.tools import config

    pinned = bool(config["db_name"])
    if pinned:
        results.record(
            PASS, "6", "cron is scoped to one database by db_name",
            f"db_name={config['db_name']}; server.py:99-100 returns it alone")
        results.record(
            GAP, "6", "cron stays scoped once dbfilter routes tenants",
            "db_name does double duty: it scopes cron AND pins routing "
            "(server.py:99-100 is `config['db_name'] or list_dbs(True)`). "
            "Unsetting it to let dbfilter route necessarily turns cron loose on "
            "every database the role can see. Needs dedicated sharded cron "
            "workers -- not a config setting (SAAS-7)")
    else:
        results.record(
            GAP, "6", "cron is scoped",
            "db_name is unset, so cron enumerates every database the role can "
            "see, ignoring dbfilter (SAAS-7)")


# ---------------------------------------------------------------------------
# spec 9 -- noisy neighbour, connection half. Arithmetic, not load.
# ---------------------------------------------------------------------------
def check_connection_budget(odoo, db, results):
    from odoo.tools import config

    with odoo.sql_db.db_connect(db).cursor() as cr:
        cr.execute("SHOW max_connections")
        server_max = int(cr.fetchone()[0])

    per_process = config["db_maxconn"]
    workers = config["workers"] or 0
    processes = max(workers, 1) + 1  # + the cron/gevent process
    worst = per_process * processes
    detail = (f"db_maxconn={per_process} x {processes} process(es) = {worst} "
              f"vs max_connections={server_max}")
    results.record(
        GAP if worst > server_max else PASS, "9",
        "the connection budget cannot be exhausted by one tenant",
        detail + ". The pool is per PROCESS and shared across databases "
                 "(sql_db.py:823), so one tenant can starve another. PgBouncer "
                 "in session mode belongs with workers>0 (SAAS-8)"
        if worst > server_max else detail)


def verify_tenant(odoo, db, other=None, indent=""):
    """Run every implemented check. Returns True when nothing FAILed."""
    results = Results(indent=indent)
    check_postgres_isolation(odoo, db, results)
    check_secret_is_distinct(odoo, db, other, results)
    check_filestore_containment(odoo, db, other, results)
    check_database_manager_closed(odoo, results)
    check_cron_scope(odoo, results)
    check_connection_budget(odoo, db, results)

    deferred = [
        ("1,2,3", "the HTTP halves: session rejection across tenants, dbfilter "
                  "by every selector, cross-tenant attachment 404",
         "needs a running server with dbfilter set and two hostnames resolving"),
        ("7", "backup and restore do not bleed",
         "needs a restore into a third database, i.e. the routing layer first"),
        ("9", "a request past limit_time_real does not slow another tenant",
         "needs load generation"),
    ]
    print("")
    print(f"{indent}deferred, not covered by this harness:")
    for spec, label, why in deferred:
        print(f"{indent}  --   [{spec}] {label}")
        print(f"{indent}       {why}")

    print("")
    ok = not results.failed
    summary = (f"{len(results.rows) - len(results.failed) - len(results.gaps)} pass, "
               f"{len(results.failed)} fail, {len(results.gaps)} known gap(s), "
               f"{len(deferred)} deferred")
    print(f"{indent}{db}: {summary}")
    if results.gaps:
        print(f"{indent}  known gaps are tracked findings, not regressions; "
              f"they do not fail this run.")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True, help="tenant database to check")
    parser.add_argument("--against", default=None,
                        help="a second tenant, to assert cross-tenant "
                             "properties such as distinct database.secret")
    args = parser.parse_args()

    try:
        odoo = load_odoo()
    except Exception as exc:  # pragma: no cover
        print(f"cannot load Odoo with this project's odoo.conf: {exc}",
              file=sys.stderr)
        return 2

    try:
        db = assert_tenant(args.db, action="check")
        other = assert_tenant(args.against, action="check") if args.against else None
    except BoundaryError as exc:
        print(exc, file=sys.stderr)
        return 1

    print("")
    return 0 if verify_tenant(odoo, db, other) else 1


if __name__ == "__main__":
    sys.exit(main())
