#!/usr/bin/env python3
"""Fail when a test file exists but nothing imports it (TST-9).

    venv\\Scripts\\python.exe tools\\check_test_wiring.py
    ./venv/bin/python3 tools/check_test_wiring.py --help

Why this exists
---------------
Odoo discovers tests by importing ``<module>/tests/__init__.py``. A ``test_*.py``
file that nothing imports is not "a test that fails" — it is a test that **does not
exist**, and there is no symptom. The suite reports ``0 failed, 0 error(s)``, exits
0, and records **zero skips**, because a skip is at least something the runner knows
about. Only the total moves, and a total is not a number anyone reads closely.

This is not hypothetical. On 2026-08-23, adding
``l10n_np/tests/test_fiscal_positions.py`` for ACC-3, I overwrote that directory's
``__init__.py`` with a single import line and silently unwired the five
``test_np_chart`` tests that were already there. The run was green, exit 0, zero
skips. The only trace was the total moving 343 → 342.

What caught it was refusing to round the total, and then counting ``def test_``
methods on disk against the number the runner reported. That count reconciles from
both directions — 347 on disk − 5 unimported = 342 run, and 343 − 5 + 4 = 342 — but
it needs a full suite run to do it, which takes minutes.

This check is the cheap static half: it needs no database, no server and no test
run, so it can sit in ``lint`` and fire in seconds. It cannot detect everything the
count can (a test method deleted from a wired file, say), so the counting check is
still worth doing after a suite run. It catches the specific failure that has
actually happened here.

It parses ``__init__.py`` with ``ast`` rather than grepping, so that
``from . import (a, b, c)`` across several lines, aliases and comments are all read
correctly — a regex over this got the parenthesised form wrong in the first draft.

Exit codes: 0 clean, 1 wiring problem found, 2 could not run.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys

#: Where to look. Vendored OCA modules are included: an unwired test there is just
#: as invisible, and `custom_addons/VENDORED.md` already tracks local deviations.
ADDON_ROOTS = ("custom_addons",)


def imported_names(init_path: pathlib.Path) -> set[str]:
    """Submodule names imported by a ``tests/__init__.py``.

    Handles ``from . import a``, ``from . import a, b``, the parenthesised
    multi-line form, and ``import x as y`` (the *source* name is what matters,
    since that is the file Odoo needs imported).
    """
    try:
        # utf-8-sig, not utf-8: six of these files start with a UTF-8 BOM (audit
        # finding QA-2). Python's own import machinery strips it, so a checker that
        # chokes on it would report a wiring problem where there is none -- which
        # is exactly what the first version of this file did.
        tree = ast.parse(init_path.read_text(encoding="utf-8-sig"),
                         filename=str(init_path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"{init_path}: {exc}") from exc

    names: set[str] = set()
    for node in ast.walk(tree):
        # `from . import x` -> level 1, module None
        if isinstance(node, ast.ImportFrom) and node.level >= 1 and node.module is None:
            names.update(alias.name for alias in node.names)
        # `from .test_x import Y` also counts: the file does get imported.
        elif isinstance(node, ast.ImportFrom) and node.level >= 1 and node.module:
            names.add(node.module.split(".")[0])
    return names


def check_module(tests_dir: pathlib.Path) -> list[str]:
    """Return a list of problems for one ``tests/`` directory."""
    problems = []
    init_path = tests_dir / "__init__.py"
    on_disk = {p.stem for p in sorted(tests_dir.glob("test_*.py"))}

    if not on_disk:
        return problems

    if not init_path.is_file():
        return [f"{len(on_disk)} test file(s) but no __init__.py, so none of them run: "
                f"{', '.join(sorted(on_disk))}"]

    imported = imported_names(init_path)

    for name in sorted(on_disk - imported):
        problems.append(
            f"{name}.py exists but __init__.py does not import it — it will not run, "
            f"and the suite will report success without it")

    # The mirror image: an import naming a file that is gone. Odoo raises
    # ImportError on load, so this is loud rather than silent -- but it is cheaper
    # to hear about it here than during a deploy.
    for name in sorted(n for n in imported - on_disk if n.startswith("test_")):
        problems.append(
            f"__init__.py imports {name}, but {name}.py does not exist — the module "
            f"will fail to load")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quiet", action="store_true",
                        help="print only modules with problems")
    args = parser.parse_args()

    repo = pathlib.Path(__file__).resolve().parent.parent
    found, checked = [], 0

    for root in ADDON_ROOTS:
        root_path = repo / root
        if not root_path.is_dir():
            continue
        for module_path in sorted(p for p in root_path.iterdir() if p.is_dir()):
            tests_dir = module_path / "tests"
            if not tests_dir.is_dir():
                continue
            checked += 1
            try:
                problems = check_module(tests_dir)
            except RuntimeError as exc:
                print(f"cannot run: {exc}", file=sys.stderr)
                return 2
            if problems:
                found.append((module_path.name, problems))
            elif not args.quiet:
                count = len(list(tests_dir.glob("test_*.py")))
                print(f"  {module_path.name:32} {count} test file(s), all wired")

    print("")
    if found:
        total = sum(len(p) for _, p in found)
        print(f"{total} test-wiring problem(s) in {len(found)} of {checked} module(s) "
              f"(TST-9):")
        for module, problems in found:
            for problem in problems:
                print(f"  {module}: {problem}")
        print("")
        print("An unimported test file is indistinguishable from one that was never")
        print("written: the suite still reports 0 failed, exit 0, and zero skips.")
        return 1

    print(f"All {checked} tests/ directory(ies) import every test file they contain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
