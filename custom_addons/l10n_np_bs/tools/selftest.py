# -*- coding: utf-8 -*-
"""Exhaustive cross-check of the Python and generated-JS calendar tables.

Replays the JS algorithm in Python against the generated bs_calendar_data.js
for EVERY day in the supported range, and compares with nepali-datetime.
A one-day drift anywhere would silently corrupt dates, so this checks all of
them rather than sampling.

    venv\\Scripts\\python.exe custom_addons/l10n_np_bs/tools/selftest.py
"""
import datetime
import os
import re
import sys

import nepali_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(os.path.dirname(HERE), "static", "src", "bs_calendar_data.js")


def load_js_table():
    src = open(JS, encoding="utf-8").read()
    min_year = int(re.search(r"BS_MIN_YEAR = (\d+)", src).group(1))
    max_year = int(re.search(r"BS_MAX_YEAR = (\d+)", src).group(1))
    ep = re.search(r"BS_EPOCH_AD = \[(\d+), (\d+), (\d+)\]", src)
    epoch = datetime.date(int(ep.group(1)), int(ep.group(2)), int(ep.group(3)))
    rows = re.findall(r"/\* (\d+) \*/ \[([0-9, ]+)\]", src)
    table = {int(y): [int(x) for x in vals.split(",")] for y, vals in rows}
    return min_year, max_year, epoch, table


def main():
    min_year, max_year, epoch, table = load_js_table()
    print(f"JS table: BS {min_year}..{max_year}, {len(table)} rows, epoch AD {epoch}")

    # Mirror of adToBs() in bs_convert.js
    def js_ad_to_bs(ad):
        remaining = (ad - epoch).days
        y = min_year
        while y <= max_year:
            total = sum(table[y])
            if remaining < total:
                break
            remaining -= total
            y += 1
        m = 1
        while m <= 12 and remaining >= table[y][m - 1]:
            remaining -= table[y][m - 1]
            m += 1
        return (y, m, remaining + 1)

    start = epoch
    end = nepali_datetime.date(max_year, 12, table[max_year][11]).to_datetime_date()
    total_days = (end - start).days + 1
    print(f"checking every day from {start} to {end}  ({total_days:,} days)")

    mismatches = []
    ad = start
    checked = 0
    while ad <= end:
        lib = nepali_datetime.date.from_datetime_date(ad)
        got = js_ad_to_bs(ad)
        if got != (lib.year, lib.month, lib.day):
            mismatches.append((ad, got, (lib.year, lib.month, lib.day)))
            if len(mismatches) > 5:
                break
        checked += 1
        ad += datetime.timedelta(days=1)

    print(f"checked {checked:,} days")
    if mismatches:
        print(f"FAIL: {len(mismatches)} mismatch(es)")
        for ad_, got, exp in mismatches[:5]:
            print(f"  {ad_}: js={got} lib={exp}")
        sys.exit(1)
    print("PASS: JS table and nepali-datetime agree on every day in range")

    # round-trip BS -> AD -> BS
    bad = 0
    for y in range(min_year, max_year + 1):
        for m in range(1, 13):
            for d in (1, table[y][m - 1]):
                ad_ = nepali_datetime.date(y, m, d).to_datetime_date()
                if js_ad_to_bs(ad_) != (y, m, d):
                    bad += 1
    print(f"round-trip on month boundaries: {'PASS' if not bad else f'FAIL ({bad})'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
