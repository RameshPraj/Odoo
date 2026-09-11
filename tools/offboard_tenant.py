#!/usr/bin/env python3
r"""Delete a tenant: dump it, drop it, and leave no residue (Phase 3, SAAS-5/12).

    venv\Scripts\python.exe tools\offboard_tenant.py --db odoo19_t_beta --dry-run
    venv\Scripts\python.exe tools\offboard_tenant.py --db odoo19_t_beta --yes
    ./venv/bin/python3 tools/offboard_tenant.py --help

This is the most destructive tool in the repository, so the guards are
structural rather than procedural -- the shape of the argument stops the wrong
database being named, instead of a check somebody might reorder or edit:

* `tenant_boundary.assert_tenant` requires `odoo19_t_<name>`. The primary
  database is `odoo19`, which **cannot be passed at all**.
* The configured `db_name` is refused independently, as a second gate.
* Maintenance databases and `ist_datahub` are refused outright.
* All of the above happen **before any connection is opened**, so a refusal
  cannot have side effects.
* `--yes` is required to drop. Without it, this is a dry run whatever else is
  passed.

**It dumps before it drops, and abandons the run if the dump fails.** Offboarding
is not a rollback-able operation, and "the customer asked us to delete it" turns
into "restore it" often enough that the dump is not optional.

What residue means here
-----------------------
`TESTING.md` test 8 specifies the assertions, and calls out the third:

    WHEN t_beta is deleted
    THEN its database is dropped
    AND  its filestore directory is gone
    AND  no session file in the shared store belongs to t_beta
    AND  its ir.mail_server credentials are revoked

    "The third assertion matters because the session store is shared (SAAS-5);
     offboarding is the point where residue is most likely."

That is right, and it is why sessions are purged by *reading* each file and
checking which database it is bound to, rather than by trusting a filename
convention -- `http.py:995` keys session files by session id alone, so the
database is inside the payload, not in the name.

`ir.mail_server` credentials live inside the dropped database, so they go with
it. The residue that outlives a drop is the filestore and the session store,
which is what this cleans.

Exit codes: 0 offboarded, 1 refused or a step failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tenant_boundary import (  # noqa: E402
    BACKUP_DIR,
    BoundaryError,
    assert_tenant,
    filestore_path,
    load_odoo,
    session_dir,
    tenant_argument,
)


def database_exists(odoo, name):
    with odoo.sql_db.db_connect("postgres").cursor() as cr:
        cr.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name])
        return bool(cr.fetchone())


def find_pg_dump():
    """Locate a `pg_dump` at least as new as the server.

    PATH first, then the standard Windows install locations. This machine has
    PostgreSQL 10, 13, 16 and 17 installed and **none of them on PATH**, so
    without this search the tool refuses every offboard -- which is safe but
    useless.

    Highest version wins, deliberately: `pg_dump` refuses to dump a server newer
    than itself, so pointing version 10 at this 17.10 cluster would fail with a
    message about server version mismatch rather than anything about backups.
    """
    on_path = shutil.which("pg_dump")
    if on_path:
        return on_path

    candidates = sorted(
        Path(r"C:\Program Files\PostgreSQL").glob("*/bin/pg_dump.exe"),
        key=lambda p: int(p.parent.parent.name) if p.parent.parent.name.isdigit() else -1,
        reverse=True,
    )
    return str(candidates[0]) if candidates else None


def dump_database(odoo, name, target):
    """pg_dump to `target`. Returns True only if a non-trivial file appeared.

    `pg_dump` rather than Odoo's `dump_db`, because the latter is gated by
    `check_db_management_enabled` and `list_db` is off (db.py:46-53, :255).
    """
    from odoo.tools import config

    binary = find_pg_dump()
    if not binary:
        print("    no pg_dump found on PATH or under "
              r"C:\Program Files\PostgreSQL, so this tenant cannot be dumped.",
              file=sys.stderr)
        return False
    print(f"    using {binary}")

    env = {"PGPASSWORD": config["db_password"] or ""}
    command = [binary, "--format=custom", f"--file={target}", "--no-password"]
    for flag, key in (("--host", "db_host"), ("--port", "db_port"),
                      ("--username", "db_user")):
        if config[key]:
            command.append(f"{flag}={config[key]}")
    command.append(name)

    import os
    # S603: argv is built here from odoo.conf plus a database name that has
    # already passed assert_tenant, and shell=False, so there is no shell to
    # inject into. Annotated rather than suppressed project-wide.
    result = subprocess.run(command, capture_output=True, text=True,  # noqa: S603
                            env={**os.environ, **env}, check=False)
    if result.returncode != 0:
        print(f"    pg_dump failed: {result.stderr.strip()[:400]}", file=sys.stderr)
        return False
    if not target.exists() or target.stat().st_size < 1024:
        print(f"    pg_dump reported success but {target} is missing or tiny.",
              file=sys.stderr)
        return False
    print(f"    dumped {target.stat().st_size:,} bytes to {target}")
    return True


def drop_database(odoo, name):
    from psycopg2 import sql

    odoo.sql_db.close_db(name)
    with odoo.sql_db.db_connect("postgres").cursor() as cr:
        cr._cnx.autocommit = True
        # Terminate stragglers first: DROP DATABASE fails while anything is
        # connected, and a half-offboarded tenant is worse than either state.
        cr.execute("""
            SELECT pg_terminate_backend(pid) FROM pg_stat_activity
             WHERE datname = %s AND pid <> pg_backend_pid()
        """, [name])
        cr.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
    print(f"    dropped database {name}")


def purge_filestore(name):
    path = filestore_path(name)
    if not path.exists():
        print(f"    no filestore at {path}")
        return
    files = sum(1 for _ in path.rglob("*") if _.is_file())
    shutil.rmtree(path)
    print(f"    removed filestore {path} ({files} file(s))")


def purge_sessions(name):
    """Delete session files bound to this database.

    The store is shared and keyed by session id (`http.py:995`), so the database
    is in the payload rather than the filename. Each file is opened and read.
    """
    directory = session_dir()
    if not directory.exists():
        print(f"    no session store at {directory}")
        return
    removed = 0
    unreadable = 0
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        try:
            blob = path.read_bytes()
        except OSError:
            unreadable += 1
            continue
        # Substring match on the raw payload rather than unpickling it: these
        # files are written by another process and deserialising one to decide
        # whether to delete it would execute its contents.
        if name.encode() in blob:
            path.unlink(missing_ok=True)
            removed += 1
    print(f"    purged {removed} session file(s) referencing {name}"
          + (f"; {unreadable} unreadable" if unreadable else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    tenant_argument(parser, "delete")
    parser.add_argument("--yes", action="store_true",
                        help="actually do it. Without this, nothing is changed")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the plan (the default behaviour anyway)")
    parser.add_argument("--skip-dump", action="store_true",
                        help="do not dump first. Deliberately awkward: this is "
                             "the only copy of the tenant's data")
    args = parser.parse_args()

    try:
        odoo = load_odoo()
    except Exception as exc:  # pragma: no cover
        print(f"cannot load Odoo with this project's odoo.conf: {exc}",
              file=sys.stderr)
        return 2

    try:
        name = assert_tenant(args.db, action="delete")
    except BoundaryError as exc:
        print(exc, file=sys.stderr)
        return 1

    exists = database_exists(odoo, name)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dump_target = BACKUP_DIR / f"{name}-offboard-{stamp}.dump"

    print("")
    print(f"offboarding {name}")
    print(f"  database exists   {exists}")
    print(f"  filestore         {filestore_path(name)}")
    print(f"  session store     {session_dir()}")
    print(f"  dump would go to  {dump_target}")

    if not args.yes:
        print("")
        print("  --yes was not given, so nothing was changed. Would:")
        print("    1. pg_dump the database" if not args.skip_dump
              else "    1. SKIP the dump (--skip-dump)")
        print("    2. terminate connections and DROP DATABASE")
        print("    3. remove the filestore directory")
        print("    4. purge session files referencing this database")
        return 0

    if not exists:
        print("")
        print(f"{name} does not exist. Cleaning up any residue anyway, since "
              f"that is the point of this tool.")

    print("")
    if exists and not args.skip_dump:
        print("  1. dumping")
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        if not dump_database(odoo, name, dump_target):
            print("")
            print("Abandoning: the dump failed, and dropping a tenant without "
                  "one destroys the only copy of their data. Fix the dump, or "
                  "pass --skip-dump if the loss is genuinely intended.",
                  file=sys.stderr)
            return 1
    elif exists:
        print("  1. skipping the dump (--skip-dump)")

    if exists:
        print("  2. dropping the database")
        drop_database(odoo, name)

    print("  3. removing the filestore")
    purge_filestore(name)

    print("  4. purging sessions")
    purge_sessions(name)

    print("")
    print(f"{name} offboarded.")
    if not args.skip_dump and exists:
        print(f"  Its dump is at {dump_target} -- the only remaining copy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
