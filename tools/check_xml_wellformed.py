#!/usr/bin/env python3
"""Parse every XML file under custom_addons with lxml, as Odoo does (COD-2).

    venv\\Scripts\\python.exe tools\\check_xml_wellformed.py
    ./venv/bin/python3 tools/check_xml_wellformed.py --help

Why this exists
---------------
A malformed data file does not degrade gracefully. Odoo aborts the module load,
and if the file is part of an asset bundle the whole merged bundle is invalid,
which takes `web.WebClient` down with it — a white screen, not a warning.

The specific trap is **``--`` inside an XML comment**, which is illegal per the XML
spec and which `lxml` rejects. It is easy to write by accident when a comment
contains a dashed list, an em-dash typed as two hyphens, or a CLI flag. It broke
files here three times in one working session.

Why a tool rather than a test
-----------------------------
There were four near-identical `test_xml_is_well_formed` methods, in `l10n_np`,
`l10n_np_tds`, `l10n_np_vat_return` and `nepali_calendar_core` — and **twelve**
modules shipping XML with no such test at all, including `l10n_np_accounting` with
six files and `local_ui_tweaks` with one. Copy-pasting a fifth and sixth time is
not the fix.

The check needs no ORM, no database and no registry: it is a filesystem walk and a
parse. Running it as an Odoo test costs a database and a module install to do
something `lxml` can do in milliseconds, and it can only ever cover modules that
already have a `tests/` directory. As a lint check it covers every module,
including those with no tests, and it runs in seconds.

Vendored OCA modules are included deliberately. Their XML is not ours to write, but
a broken file there breaks this installation exactly as hard.

**One thing this does not replace.** `minidom` used to be used for this in some
copies and accepts `--` in comments, so it would pass a file Odoo rejects. That is
why this uses `lxml.etree` — the same parser Odoo's `tools/convert.py` uses. If
this file is ever rewritten, keep that.

Exit codes: 0 clean, 1 malformed XML found, 2 could not run.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

try:
    from lxml import etree
except ImportError:  # pragma: no cover - lxml is an Odoo dependency
    print("cannot run: lxml is not installed", file=sys.stderr)
    sys.exit(2)

#: Directories to walk.
ADDON_ROOTS = ("custom_addons",)

#: Skipped wholesale: build output and caches, never hand-written.
SKIP_PARTS = {"__pycache__", "node_modules", ".git"}


def xml_files(root: pathlib.Path):
    for path in sorted(root.rglob("*.xml")):
        if SKIP_PARTS.intersection(path.parts):
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quiet", action="store_true",
                        help="print only modules with malformed files")
    args = parser.parse_args()

    repo = pathlib.Path(__file__).resolve().parent.parent
    broken, checked, modules = [], 0, 0

    for root in ADDON_ROOTS:
        root_path = repo / root
        if not root_path.is_dir():
            continue
        for module_path in sorted(p for p in root_path.iterdir() if p.is_dir()):
            paths = list(xml_files(module_path))
            if not paths:
                continue
            modules += 1
            module_broken = []
            for path in paths:
                checked += 1
                try:
                    etree.parse(str(path))
                except etree.XMLSyntaxError as exc:
                    module_broken.append((path.relative_to(repo), str(exc)))
            if module_broken:
                broken.extend(module_broken)
            elif not args.quiet:
                print(f"  {module_path.name:32} {len(paths)} XML file(s) parse")

    print("")
    if broken:
        print(f"{len(broken)} malformed XML file(s) of {checked} checked (COD-2):")
        for path, message in broken:
            print(f"  {path}")
            print(f"      {message}")
        print("")
        print("Odoo aborts the module load on any of these. If the file belongs to an")
        print("asset bundle, the whole merged bundle is invalid and web.WebClient")
        print("fails with it. A '--' inside a comment is the usual cause.")
        return 1

    print(f"All {checked} XML file(s) across {modules} module(s) parse with lxml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
