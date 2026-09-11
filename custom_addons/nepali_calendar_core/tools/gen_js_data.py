# -*- coding: utf-8 -*-
"""Generate the JavaScript Bikram Sambat table from nepali-datetime's CSV.

Both the Python and JS sides of this module MUST use the same month-length
table, or a date shown in the browser will not match what the server stores.
Rather than maintaining two copies, the JS file is generated from the CSV that
ships with nepali-datetime.

    venv\\Scripts\\python.exe custom_addons/nepali_calendar_core/tools/gen_js_data.py
"""
import csv
import datetime
import importlib.util
import os
import sys

import nepali_datetime
from nepali_datetime import config

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "static", "src", "bs_calendar_data.js")


def _load_names():
    """Load ``names.py`` by path.

    This script runs outside an Odoo process, so ``from .names import ...`` is
    not available -- there is no package context. Loading by path keeps the name
    tables in exactly one file while still letting the generator run standalone.
    ``names.py`` imports nothing, which is what makes this safe.
    """
    path = os.path.join(HERE, "names.py")
    spec = importlib.util.spec_from_file_location("_bs_names", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _js_array(name, values, comment=None, per_line=6):
    """Render a Python list of strings as an exported JS array."""
    out = []
    if comment:
        out.append(comment)
    out.append(f"export const {name} = [")
    # `None` pads the 1-based month lists on the Python side; JS indexes months
    # 0-based via `BS_MONTHS_NE[month - 1]`, so the padding is dropped here.
    items = [v for v in values if v is not None]
    for i in range(0, len(items), per_line):
        chunk = ", ".join(f'"{v}"' for v in items[i:i + per_line])
        out.append(f"    {chunk},")
    out.append("];")
    out.append("")
    return out


def main():
    with open(config.CALENDAR_PATH, encoding="utf-8") as fh:
        rows = list(csv.reader(fh))

    header, data = rows[0], rows[1:]
    if len(header) != 13:
        sys.exit(f"unexpected CSV shape: {header}")

    years = {}
    for row in data:
        if not row or not row[0].strip():
            continue
        years[int(row[0])] = [int(x) for x in row[1:13]]

    min_year, max_year = min(years), max(years)

    # Anchor: the Gregorian date corresponding to BS min_year-01-01.
    epoch = nepali_datetime.date(min_year, 1, 1).to_datetime_date()

    # Self-check: walk the table and confirm it reproduces the library's own
    # conversion at several points. If this fails the generated JS would be
    # wrong, so fail loudly rather than emit a broken file.
    probes = [
        datetime.date(1950, 1, 1), datetime.date(2000, 1, 1),
        datetime.date(2026, 9, 9), datetime.date(2030, 12, 31),
        datetime.date(2043, 1, 1),
    ]
    offset_ok = True
    for ad in probes:
        bs = nepali_datetime.date.from_datetime_date(ad)
        days = (ad - epoch).days
        # replay the table
        y, remaining = min_year, days
        while y <= max_year and remaining >= sum(years[y]):
            remaining -= sum(years[y])
            y += 1
        m = 1
        while m <= 12 and remaining >= years[y][m - 1]:
            remaining -= years[y][m - 1]
            m += 1
        d = remaining + 1
        if (y, m, d) != (bs.year, bs.month, bs.day):
            print(f"  MISMATCH {ad}: table={(y, m, d)} lib={(bs.year, bs.month, bs.day)}")
            offset_ok = False
    if not offset_ok:
        sys.exit("table replay disagrees with nepali-datetime -- refusing to generate")
    print(f"table replay verified at {len(probes)} probe dates")

    lines = [
        "/** GENERATED FILE -- DO NOT EDIT BY HAND.",
        " *",
        " * Bikram Sambat month lengths, generated from the calendar_bs.csv that",
        " * ships with the nepali-datetime Python package, so that the browser and",
        " * the server always agree.",
        " *",
        " * Regenerate with:",
        " *   venv\\Scripts\\python.exe custom_addons/nepali_calendar_core/tools/gen_js_data.py",
        " */",
        "",
        f"export const BS_MIN_YEAR = {min_year};",
        f"export const BS_MAX_YEAR = {max_year};",
        "",
        "// Gregorian date corresponding to BS %d-01-01, as [year, month(1-12), day]" % min_year,
        f"export const BS_EPOCH_AD = [{epoch.year}, {epoch.month}, {epoch.day}];",
        "",
        "// BS_MONTH_DAYS[year - BS_MIN_YEAR] = [days in Baisakh .. days in Chaitra]",
        "export const BS_MONTH_DAYS = [",
    ]
    for y in range(min_year, max_year + 1):
        lines.append(f"    /* {y} */ [{', '.join(str(v) for v in years[y])}],")
    lines += ["];", ""]

    # Names are emitted from tools/names.py rather than written out here, so the
    # generator cannot disagree with the Python side it is supposed to mirror.
    names = _load_names()
    lines += _js_array("BS_MONTHS_NE", names.MONTHS_NE)
    lines += _js_array("BS_MONTHS_EN", names.MONTHS_EN)
    lines += _js_array(
        "BS_WEEKDAYS_NE_SHORT", names.WEEKDAYS_NE_SHORT, per_line=7,
        comment="// Sunday first -- Bikram Sambat weeks start on Sunday",
    )
    lines += _js_array("BS_WEEKDAYS_NE_LONG", names.WEEKDAYS_NE_LONG, per_line=7)
    lines += [
        "// Historical alias: the picker imported the short form under this name.",
        "export const BS_WEEKDAYS_NE = BS_WEEKDAYS_NE_SHORT;",
        "",
        "// Saturday, not Sunday, is the weekly holiday in Nepal.",
        f"export const BS_WEEKEND_WEEKDAY = {names.WEEKEND_WEEKDAY};",
        "",
        "// Devanagari digits, index 0..9.",
        f'export const BS_NP_DIGITS = "{names.NP_DIGITS}";',
        "",
    ]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))

    print(f"wrote {OUT}")
    print(f"  BS years {min_year}..{max_year} ({len(years)} rows)")
    print(f"  epoch: BS {min_year}-01-01 == AD {epoch}")


if __name__ == "__main__":
    main()
