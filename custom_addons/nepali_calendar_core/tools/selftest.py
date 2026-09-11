# -*- coding: utf-8 -*-
"""Exhaustive cross-check of the Python and generated-JS calendar tables.

Replays the JS algorithm in Python against the generated ``bs_calendar_data.js``
and compares every day with nepali-datetime. A one-day drift anywhere would
silently corrupt dates, so this checks all of them rather than sampling.

The work is exposed as :func:`check`, which *returns* its findings instead of
printing and exiting, so the test suite can assert on it. Previously the only
caller was ``main()``, which meant this ran when somebody remembered to run it by
hand -- which is to say, never.

    venv\\Scripts\\python.exe custom_addons/nepali_calendar_core/tools/selftest.py
"""
import datetime
import os
import re
import sys

import nepali_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(os.path.dirname(HERE), "static", "src", "bs_calendar_data.js")


def load_js_table(path=JS):
    """Parse the generated JS table back into Python.

    Reading the *generated artefact* rather than the generator is the point: it
    catches a stale checked-in file, which is the failure mode that actually
    happens.
    """
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    min_year = int(re.search(r"BS_MIN_YEAR = (\d+)", src).group(1))
    max_year = int(re.search(r"BS_MAX_YEAR = (\d+)", src).group(1))
    ep = re.search(r"BS_EPOCH_AD = \[(\d+), (\d+), (\d+)\]", src)
    epoch = datetime.date(int(ep.group(1)), int(ep.group(2)), int(ep.group(3)))
    rows = re.findall(r"/\* (\d+) \*/ \[([0-9, ]+)\]", src)
    table = {int(y): [int(x) for x in vals.split(",")] for y, vals in rows}
    return min_year, max_year, epoch, table


def _js_ad_to_bs_factory(min_year, max_year, epoch, table):
    """A faithful transcription of ``adToBs()`` in bs_convert.js."""

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

    return js_ad_to_bs


def check(sample_every=1, max_mismatches=5, path=JS):
    """Compare the JS table against nepali-datetime.

    :param sample_every: check every Nth day. 1 is the full 46,000-day sweep;
        the test suite uses a larger stride for its fast case and 1 for the
        nightly one. Month boundaries are always checked in full regardless,
        because that is where an off-by-one hides.
    :param max_mismatches: stop collecting after this many, so a systematically
        broken table does not produce a 46,000-line report.
    :returns: ``{'min_year', 'max_year', 'epoch', 'start', 'end', 'checked',
        'mismatches', 'boundary_mismatches'}``. Both mismatch lists empty means
        the tables agree.
    """
    min_year, max_year, epoch, table = load_js_table(path)
    js_ad_to_bs = _js_ad_to_bs_factory(min_year, max_year, epoch, table)

    start = epoch
    end = nepali_datetime.date(max_year, 12, table[max_year][11]).to_datetime_date()

    mismatches = []
    checked = 0
    ad = start
    step = datetime.timedelta(days=sample_every)
    while ad <= end:
        lib = nepali_datetime.date.from_datetime_date(ad)
        got = js_ad_to_bs(ad)
        if got != (lib.year, lib.month, lib.day):
            mismatches.append((ad, got, (lib.year, lib.month, lib.day)))
            if len(mismatches) >= max_mismatches:
                break
        checked += 1
        ad += step

    # Round trip BS -> AD -> BS on the first and last day of every month. Always
    # exhaustive: a wrong month length shows up here and nowhere else.
    boundary = []
    for y in range(min_year, max_year + 1):
        for m in range(1, 13):
            for d in (1, table[y][m - 1]):
                ad_ = nepali_datetime.date(y, m, d).to_datetime_date()
                got = js_ad_to_bs(ad_)
                if got != (y, m, d):
                    boundary.append(((y, m, d), got))
                    if len(boundary) >= max_mismatches:
                        break

    return {
        'min_year': min_year,
        'max_year': max_year,
        'epoch': epoch,
        'start': start,
        'end': end,
        'checked': checked,
        'mismatches': mismatches,
        'boundary_mismatches': boundary,
    }


def main():
    result = check()
    print(
        f"JS table: BS {result['min_year']}..{result['max_year']}, "
        f"epoch AD {result['epoch']}"
    )
    print(f"checked {result['checked']:,} days "
          f"({result['start']} .. {result['end']})")

    ok = True
    if result['mismatches']:
        ok = False
        print(f"FAIL: {len(result['mismatches'])} day mismatch(es)")
        for ad_, got, exp in result['mismatches']:
            print(f"  {ad_}: js={got} lib={exp}")
    else:
        print("PASS: JS table and nepali-datetime agree on every day in range")

    if result['boundary_mismatches']:
        ok = False
        print(f"FAIL: {len(result['boundary_mismatches'])} month-boundary "
              f"round-trip failure(s)")
        for bs, got in result['boundary_mismatches']:
            print(f"  BS {bs} -> AD -> {got}")
    else:
        print("PASS: round-trip on every month boundary")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
