# -*- coding: utf-8 -*-
r"""The tenant naming boundary, in one place, for every tool that can destroy data.

Three tools create, harden and delete tenant databases on a cluster this project
**shares with another team**. The rule that keeps them off `ist_datahub` and off
the primary `odoo19` database should exist once, not three times, because a guard
copied three times is a guard that will disagree with itself.

Two independent gates, deliberately not one:

1. **The name must look like a tenant.** `odoo19_t_<something>`. The primary
   database is `odoo19`, which does not match, so it cannot be passed to a
   destructive tool *at all* -- the protection is the shape of the argument
   rather than a check somebody might later edit or reorder.
2. **The name must not be the configured primary.** Read from `odoo.conf`'s
   `db_name` at run time, so if that ever changes the guard follows it.

Both are checked before any connection is opened, so a refusal cannot have side
effects. And neither depends on me remembering: the earlier `harden_database.py`
made the same argument and this generalises it.

`ist_datahub` is unreachable three times over -- it fails gate 1, and PostgreSQL
would refuse the statements anyway because the `odoo` role is not a superuser and
does not own it. That belt-and-braces is intentional: the *intent* should be
visible in the source, not only enforced at the far end.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: A tenant database. Note what this does NOT match: `odoo19`, the primary.
TENANT_NAME = re.compile(r"^odoo19_t_[a-z0-9][a-z0-9_]*$")

#: Never, under any circumstances, and independently of the pattern above.
REFUSED_OUTRIGHT = frozenset({"postgres", "template0", "template1", "ist_datahub"})

#: Where offboarding writes its safety dump. Outside the OneDrive tree (DAT-1).
BACKUP_DIR = Path(r"C:\Users\i81129\odoo-backups")


class BoundaryError(Exception):
    """Raised when a database name is outside what a tool may touch."""


def load_odoo(argv_extra=None):
    """Import Odoo with this project's odoo.conf, returning the module.

    Centralised because every tool needs the same three steps in the same order,
    and because getting the config load wrong yields credentials-not-found errors
    that look like database problems.
    """
    sys.path.insert(0, str(REPO))
    import odoo
    from odoo.tools import config

    config.parse_config(["-c", str(REPO / "odoo.conf")] + list(argv_extra or []))
    return odoo


def primary_database():
    """The database this project actually runs on, from odoo.conf."""
    from odoo.tools import config

    return config["db_name"]


def assert_tenant(name, *, action):
    """Refuse anything that is not a tenant database. Raises BoundaryError.

    :param action: what the caller is about to do, quoted back in the refusal so
        the message says which tool refused and why.
    """
    if name in REFUSED_OUTRIGHT:
        raise BoundaryError(
            f"refusing to {action} {name!r}: it is a maintenance database or "
            f"another team's, and is never a valid target."
        )
    if not TENANT_NAME.match(name or ""):
        raise BoundaryError(
            f"refusing to {action} {name!r}: tenant databases are named "
            f"odoo19_t_<name>. The primary database does not match that shape on "
            f"purpose, so it cannot be passed to a destructive tool."
        )
    primary = primary_database()
    if primary and name == primary:
        raise BoundaryError(
            f"refusing to {action} {name!r}: odoo.conf names it as the primary "
            f"database (db_name)."
        )
    return name


def tenant_argument(parser, action):
    """Add the `--db` argument every tool shares.

    Never defaulted. A destructive-sounding default on a shared cluster is how
    the wrong database gets touched, and the wrappers already establish that a
    database target is always explicit.
    """
    parser.add_argument(
        "--db", required=True,
        help=f"tenant database to {action}; must be named odoo19_t_<name>")
    return parser


def filestore_path(name):
    from odoo.tools import config

    return Path(config.filestore(name))


def session_dir():
    from odoo.tools import config

    return Path(config.session_dir)
