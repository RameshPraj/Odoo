#!/usr/bin/env python3
r"""Fail when BACKLOG.md's stated finding counts disagree with its own contents (DOC-5).

    venv\Scripts\python.exe tools\check_backlog_counts.py
    ./venv/bin/python3 tools/check_backlog_counts.py --help

Why this exists
---------------
``BACKLOG.md`` states how many findings are resolved, partial and open. That sentence
has now been wrong **three times**, each time in the same way: an entry was marked
resolved in place and the total at the top was not re-typed.

The document already carries a note about this, added the first time it happened:

    "The lesson is not 'be careful' — it is that a total maintained by hand will
    drift. Count it from the document; do not carry it forward."

The note was right and it did not help, because a note cannot count. Two later
recounts drifted again — on 2026-08-23 the header said 27 resolved while the body
marked 31 (COD-2, TST-2 and TST-3 were missing), and OPS-6 was listed as PARTIAL
with no PARTIAL marker in its own entry. A prose instruction to derive a number is
not a mechanism for deriving it.

This is that mechanism. It re-derives the counts and fails when the stated figures
disagree, so the drift becomes a lint failure at the moment it is introduced rather
than a discovery months later. It is deliberately not a formatter: it does not edit
the document, because the correct fix for a wrong count is sometimes a wrong
*status*, and only a human can tell which.

How a status is decided
-----------------------
Findings appear in two shapes, and both are read:

* **Section form** — ``## <ID> · title`` followed within a few lines by a status
  such as ``**RESOLVED 2026-08-14**`` or ``**CONFIRMED**``.
* **Table form** — ``| **<ID>** | <status cell> | <category> | …``.

A table row is authoritative only when the section form is absent or says OPEN, so a
finding written up in full and later summarised in a table cannot be silently
downgraded.

**Partial is checked before resolved, and matches three spellings.** The document
says ``PARTLY RESOLVED`` (TST-7), ``PARTIALLY RESOLVED`` (CI-1) and ``PARTIALLY
ADDRESSED`` (CI-2) for the same state. A first draft of this check matched only the
first, which filed CI-1 as fully resolved and CI-2 as open, and produced 33/1/87
against a true 31/3/87 — the same class of error it exists to catch, found by
disagreeing with a count done by hand minutes earlier. Order matters too, since
``RESOLVED`` is a substring of ``PARTIALLY RESOLVED``.

Getting this wrong is also how the 2026-08-23 roll-up listed **OPS-6** as partial:
its entry says plainly ``**CONFIRMED (by inspection)**``, so it is open, and always
was.

Exit codes: 0 counts agree, 1 they disagree, 2 could not run.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DOC = REPO / "docs" / "project-review" / "BACKLOG.md"

ID_RE = re.compile(r"^[A-Z]{2,6}-\d+$")
HEADING_RE = re.compile(r"^##+\s+\*{0,2}([A-Z]{2,6}-\d+)\*{0,2}\s*[·:—-]\s*(.+?)\s*$")
#: The roll-up sentence, e.g. "**31 RESOLVED, 3 PARTIAL (CI-1, CI-2, TST-7), 87 OPEN**".
#: The parenthetical names the partial findings and therefore contains commas, so
#: `[^,]*` cannot be used to skip it -- the first draft did, matched nothing, and
#: reported "states no derived counts" against a document that stated them.
STATED_RE = re.compile(
    r"\*\*(\d+)\s+RESOLVED,\s*(\d+)\s+PARTIAL(?:\s*\([^)]*\))?,\s*(\d+)\s+OPEN\*\*",
    re.I)

#: The three spellings the document uses for the partial state. See the module
#: docstring: matching only the first produced 33/1/87 against a true 31/3/87.
PARTIAL_RE = re.compile(r"PART(?:LY|IALLY)\s+(?:RESOLVED|CLOSED|ADDRESSED)", re.I)

#: Status lookahead. Long enough to clear a blank line and a category line, short
#: enough not to reach the next entry.
LOOKAHEAD = 8


def classify(text: str) -> str:
    """Partial before resolved: the latter is a substring of the former."""
    if PARTIAL_RE.search(text):
        return "PARTLY"
    if re.search(r"\bRESOLVED\b|\bCLOSED\b", text):
        return "RESOLVED"
    return "OPEN"


def parse(doc: Path) -> dict[str, str]:
    lines = doc.read_text(encoding="utf-8").splitlines()
    statuses: dict[str, str] = {}

    # Section form.
    current: str | None = None
    buffer: list[str] = []
    for line in [*lines, "## __EOF__ · sentinel"]:
        match = HEADING_RE.match(line)
        if match or line.startswith("## "):
            if current:
                statuses[current] = classify("\n".join(buffer[:LOOKAHEAD]))
            current = match.group(1) if match else None
            buffer = []
        elif current:
            buffer.append(line)

    # Table form, authoritative only where the section form is absent or OPEN.
    for line in lines:
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        finding = cells[0].strip("* ")
        if not ID_RE.match(finding):
            continue
        if statuses.get(finding, "OPEN") == "OPEN":
            statuses[finding] = classify(cells[1])

    return statuses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--quiet", action="store_true",
                        help="only report a mismatch")
    args = parser.parse_args()

    if not args.doc.is_file():
        print(f"cannot read {args.doc}", file=sys.stderr)
        return 2

    statuses = parse(args.doc)
    if not statuses:
        print(f"no findings parsed out of {args.doc} -- has its format changed?",
              file=sys.stderr)
        return 2

    derived = {
        "RESOLVED": sum(1 for s in statuses.values() if s == "RESOLVED"),
        "PARTLY": sum(1 for s in statuses.values() if s == "PARTLY"),
        "OPEN": sum(1 for s in statuses.values() if s == "OPEN"),
    }

    text = args.doc.read_text(encoding="utf-8")
    stated_match = STATED_RE.search(text)
    if not stated_match:
        print("")
        print(f"{args.doc.name} states no derived counts, so nothing can be checked.")
        print("Add a sentence of the form:")
        print("  **<n> RESOLVED, <n> PARTIAL (…), <n> OPEN**")
        print(f"Derived now: {derived['RESOLVED']} RESOLVED, "
              f"{derived['PARTLY']} PARTIAL, {derived['OPEN']} OPEN "
              f"({len(statuses)} findings).")
        return 1

    stated = {
        "RESOLVED": int(stated_match.group(1)),
        "PARTLY": int(stated_match.group(2)),
        "OPEN": int(stated_match.group(3)),
    }

    if not args.quiet:
        print("")
        print(f"{args.doc.name}: {len(statuses)} findings")
        for key in ("RESOLVED", "PARTLY", "OPEN"):
            flag = "ok" if stated[key] == derived[key] else "MISMATCH"
            print(f"  {key:9} stated {stated[key]:3}   derived {derived[key]:3}   {flag}")

    wrong = [k for k in stated if stated[k] != derived[k]]
    if wrong:
        print("")
        print(f"{args.doc.name}'s stated counts have drifted from its contents:")
        for key in wrong:
            print(f"  {key}: says {stated[key]}, document contains {derived[key]}")
        print("")
        print("Either an entry's status changed without the roll-up being updated, or")
        print("the roll-up was edited without the entry. Fix whichever is wrong -- this")
        print("check deliberately does not edit the document, because a wrong count")
        print("sometimes means a wrong status, and only a human can tell which.")
        return 1

    if not args.quiet:
        print("")
    print(f"BACKLOG.md's stated counts match its contents "
          f"({derived['RESOLVED']} resolved, {derived['PARTLY']} partial, "
          f"{derived['OPEN']} open).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
