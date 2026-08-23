#!/usr/bin/env python3
"""Fail when a local module changed without its manifest version being bumped (UPG-2).

    venv\\Scripts\\python.exe tools\\check_module_versions.py
    ./venv/bin/python3 tools/check_module_versions.py --help

Why this exists
---------------
Odoo runs a migration, and reloads a module's data, only when the manifest version
**rises**. UPG-2 recorded the consequence: with every module frozen at
``19.0.1.0.0``, deploying new code depends on someone remembering ``-u``. Forget it
and the database keeps the old views, menus and **access rights** while the source
has moved on. Stale ACLs are the part that matters.

Bumping the versions once fixes today and nothing else -- the next change
reintroduces the drift. So this is the check rather than the bump: for each module
it compares the last commit that touched *any* tracked file in the module against
the last commit that touched the ``version`` line of its manifest. If the module is
newer than its own version, the version is stale.

What it deliberately does not do
--------------------------------
It does not look at the working tree. Uncommitted edits are how you work; the
question is whether what you are about to *commit or deploy* carries a version that
moved. Run it before pushing, or in CI over the pushed range.

**Deliberately conservative.** Strictly, only a change to *data* -- views, menus,
ACLs, record rules, chart templates -- or a new migration needs the version to move;
a pure-Python change takes effect on restart regardless. This check does not try to
tell those apart, because reading a diff and deciding "no data changed here" is
exactly the judgement that goes wrong quietly, and a bump costs nothing. Expect it
to flag changes that did not strictly need one.

It only reads ``git log``, so it is safe to run anywhere and needs no database.

Exit codes: 0 clean, 1 drift found, 2 could not run (not a git repo, no git).
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

#: Directories holding modules whose versions we control. Vendored OCA modules are
#: included on purpose: a local edit to one of them has exactly the same upgrade
#: problem, and VENDORED.md already tracks that we carry local deviations.
ADDON_ROOTS = ("custom_addons",)

VERSION_RE = re.compile(r"""["']version["']\s*:""")


def git(*args: str, cwd: pathlib.Path) -> str:
    # S603/S607: "git" is resolved from PATH rather than an absolute path, and the
    # arguments are literals from this file plus commit hashes that git itself
    # produced. There is no shell and no external input, and pinning an absolute
    # git path would break the moment this ran on another machine.
    result = subprocess.run(  # noqa: S603
        ("git", *args),  # noqa: S607
        cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def last_commit_touching(repo: pathlib.Path, path: str) -> str | None:
    out = git("log", "-1", "--format=%H", "--", path, cwd=repo)
    return out or None


def last_commit_changing_version(repo: pathlib.Path, manifest: str) -> str | None:
    """The last commit whose diff of `manifest` touched the version line.

    ``git log -L`` would be the obvious tool but it needs a stable line range, and
    the version line moves. Walking the manifest's own history and inspecting each
    patch is slower and correct.
    """
    commits = git("log", "--format=%H", "--", manifest, cwd=repo).splitlines()
    for commit in commits:
        patch = git("show", "--format=", "--unified=0", commit, "--", manifest,
                    cwd=repo)
        for line in patch.splitlines():
            is_change = (line.startswith(("+", "-"))
                         and not line.startswith(("+++", "---")))
            if is_change and VERSION_RE.search(line):
                return commit
    return None


def commit_order(repo: pathlib.Path) -> dict[str, int]:
    """Map commit hash -> position in first-parent history, newest = 0.

    Comparing dates would be wrong: rebases and cherry-picks make author dates
    non-monotonic. Topological position is what "newer" means here.
    """
    order = {}
    for index, sha in enumerate(git("log", "--format=%H", cwd=repo).splitlines()):
        order[sha] = index
    return order


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quiet", action="store_true",
                        help="print only modules with stale versions")
    args = parser.parse_args()

    repo = pathlib.Path(__file__).resolve().parent.parent
    try:
        git("rev-parse", "--git-dir", cwd=repo)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return 2

    order = commit_order(repo)
    stale, checked = [], 0

    for root in ADDON_ROOTS:
        root_path = repo / root
        if not root_path.is_dir():
            continue
        for module_path in sorted(p for p in root_path.iterdir() if p.is_dir()):
            manifest = module_path / "__manifest__.py"
            if not manifest.is_file():
                continue
            module = module_path.name
            checked += 1
            rel_module = f"{root}/{module}"
            rel_manifest = f"{rel_module}/__manifest__.py"

            newest_file = last_commit_touching(repo, rel_module)
            newest_version = last_commit_changing_version(repo, rel_manifest)

            if newest_file is None:
                # Never committed: nothing to compare, and nothing deployed either.
                if not args.quiet:
                    print(f"  {module:32} untracked, skipped")
                continue
            if newest_version is None:
                stale.append((module, "its version line has never been committed"))
                continue

            # Lower index == newer, since git log lists newest first.
            if order.get(newest_file, 1 << 30) < order.get(newest_version, 1 << 30):
                stale.append((
                    module,
                    f"changed in {newest_file[:8]} but the version last moved in "
                    f"{newest_version[:8]}"))
            elif not args.quiet:
                print(f"  {module:32} version is current")

    print("")
    if stale:
        print(f"{len(stale)} of {checked} module(s) have a stale manifest version "
              f"(UPG-2):")
        for module, reason in stale:
            print(f"  {module}: {reason}")
        print("")
        print("Bump the version in the manifest. Odoo reloads a module's data, and")
        print("runs its migrations, only when the version rises -- otherwise the")
        print("database keeps the old views, menus and access rights.")
        return 1

    print(f"All {checked} module version(s) are newer than their last code change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
