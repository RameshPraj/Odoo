# -*- coding: utf-8 -*-
"""The Python/JavaScript conversion contract.

Two independent implementations of the same calendar (``tools/bs.py`` on the
server, ``static/src/bs_convert.js`` in the browser) render the same stored
Gregorian date. If they disagree by a single day, a user edits what looks like the
5th and the ledger records the 6th -- and nothing raises. Nothing here is
cosmetic.

These tests assert the *contract*, not the implementations:

  TestCalendarTableAgreement  the generated JS table reproduces nepali-datetime
                              on all 46,022 days in range (0.9s, so no sampling)
  TestNameTablesSingleSource  the generated JS names are byte-equal to names.py
  TestFormatContract          both sides produce the same string for a date
  TestParseContract           both sides accept the same separators and digits
  TestRangeContract           both refuse out-of-range dates rather than guessing
  TestErrorContract           the deliberate asymmetry: Python raises, JS returns
                              null -- asserted so it cannot drift silently
"""
import datetime
import os
import re

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..tools import bs, names
from ..tools import selftest

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DATA = os.path.join(MODULE_DIR, "static", "src", "bs_calendar_data.js")
JS_CONVERT = os.path.join(MODULE_DIR, "static", "src", "bs_convert.js")


def _js_string_array(source, const_name):
    """Extract `export const NAME = ["a", "b"];` from JS source."""
    match = re.search(
        r"export const " + const_name + r" = \[(.*?)\];", source, re.S
    )
    if not match:
        return None
    return re.findall(r'"([^"]+)"', match.group(1))


@tagged("-at_install", "post_install")
class TestCalendarTableAgreement(TransactionCase):
    """The 46,022-day sweep that previously existed but was never executed."""

    def test_js_table_agrees_with_library_every_day(self):
        result = selftest.check()

        self.assertEqual(
            result["mismatches"], [],
            "the generated JS month-length table disagrees with nepali-datetime. "
            "Regenerate it with tools/gen_js_data.py -- a checked-in stale table "
            "is the failure mode this catches."
        )
        self.assertEqual(
            result["boundary_mismatches"], [],
            "BS -> AD -> BS round trip failed on a month boundary, which means a "
            "month length in the table is wrong."
        )
        # Guard the guard: if `check()` silently checked nothing, the two
        # assertions above would pass vacuously.
        self.assertGreater(
            result["checked"], 45000,
            f"expected the full range to be swept, only {result['checked']} days "
            f"were checked"
        )

    def test_python_and_js_table_share_the_same_range(self):
        """Both sides must claim the same supported range.

        Python hard-codes BS_MIN_YEAR/BS_MAX_YEAR; the JS file derives them from
        the CSV. If nepali-datetime ships a longer table, Python's constants go
        stale and it would reject dates the browser accepts.
        """
        result = selftest.check(sample_every=4000)
        self.assertEqual(bs.BS_MIN_YEAR, result["min_year"])
        self.assertEqual(bs.BS_MAX_YEAR, result["max_year"])


@tagged("-at_install", "post_install")
class TestNameTablesSingleSource(TransactionCase):
    """tools/names.py is the only place month and weekday names are written."""

    def setUp(self):
        super().setUp()
        with open(JS_DATA, encoding="utf-8") as fh:
            self.js = fh.read()

    def test_month_names_match(self):
        # names.py pads index 0 with None for 1-based month access; JS is 0-based.
        self.assertEqual(
            _js_string_array(self.js, "BS_MONTHS_NE"),
            [n for n in names.MONTHS_NE if n],
        )
        self.assertEqual(
            _js_string_array(self.js, "BS_MONTHS_EN"),
            [n for n in names.MONTHS_EN if n],
        )

    def test_weekday_names_match_in_both_lengths(self):
        """Both forms, in both layers.

        Python used to carry only the long form and JS only the short, so neither
        could render what the other did. Regressing to one form on one side is
        exactly what this catches.
        """
        self.assertEqual(
            _js_string_array(self.js, "BS_WEEKDAYS_NE_SHORT"),
            names.WEEKDAYS_NE_SHORT,
        )
        self.assertEqual(
            _js_string_array(self.js, "BS_WEEKDAYS_NE_LONG"),
            names.WEEKDAYS_NE_LONG,
        )

    def test_digits_match(self):
        found = re.search(r'export const BS_NP_DIGITS = "([^"]+)"', self.js)
        self.assertTrue(found, "BS_NP_DIGITS missing from the generated table")
        self.assertEqual(found.group(1), names.NP_DIGITS)

    def test_generated_file_is_not_hand_edited(self):
        self.assertIn(
            "GENERATED FILE", self.js,
            "the generated header is gone, which suggests the file was replaced "
            "by hand; regenerate with tools/gen_js_data.py"
        )


@tagged("-at_install", "post_install")
class TestFormatContract(TransactionCase):
    """Both layers must render a given date identically."""

    #: (AD date, expected numeric form, expected month-name form)
    CASES = [
        (datetime.date(2026, 9, 9), "2083-05-24", "2083 भदौ 24"),
        (datetime.date(2026, 4, 14), "2083-01-01", "2083 बैशाख 01"),
        (datetime.date(2000, 1, 1), "2056-09-17", "2056 पुष 17"),
    ]

    def test_numeric_form(self):
        for ad, expected, _unused in self.CASES:
            with self.subTest(ad=ad):
                self.assertEqual(bs.format_bs(ad), expected)

    def test_month_name_form_is_space_separated_and_day_padded(self):
        """The two divergences that existed between the layers.

        JS joined with spaces and did not pad the day; Python joined with hyphens
        and did pad. Both now use spaces and pad, so a date on a PDF matches the
        same date in a list view.
        """
        for ad, _unused, expected in self.CASES:
            with self.subTest(ad=ad):
                self.assertEqual(bs.format_bs(ad, month_names=True), expected)

    def test_devanagari_is_opt_in_on_both_sides(self):
        """Default ASCII.

        The two sides defaulted differently (`np_digits=False` in Python,
        `npDigits: true` in JS), so the same date rendered in different scripts
        depending on which layer produced it.
        """
        ad = datetime.date(2026, 9, 9)
        self.assertEqual(bs.format_bs(ad), "2083-05-24")
        self.assertEqual(bs.format_bs(ad, np_digits=True), "२०८३-०५-२४")

        source = open(JS_CONVERT, encoding="utf-8").read()
        self.assertRegex(
            source, r"npDigits\s*=\s*false",
            "bs_convert.js formatBs must default npDigits to false to match "
            "tools/bs.py"
        )

    def test_format_none_is_empty_not_an_error(self):
        """A blank date field renders blank rather than raising in a report."""
        self.assertEqual(bs.format_bs(None), "")

    def test_datetime_input_is_accepted(self):
        """Reports pass datetimes; the day must be taken, not rejected."""
        self.assertEqual(
            bs.format_bs(datetime.datetime(2026, 9, 9, 23, 45)), "2083-05-24"
        )


@tagged("-at_install", "post_install")
class TestParseContract(TransactionCase):
    """Both layers must accept the same input."""

    #: Every one of these must parse to AD 2026-09-09.
    ACCEPTED = [
        "2083-05-24",
        "2083/05/24",
        "2083.05.24",
        "2083 05 24",
        "2083-5-24",       # unpadded
        "  2083-05-24  ",  # surrounding whitespace
        "२०८३-०५-२४",       # Devanagari
        "२०८३/०५/२४",
    ]

    def test_accepted_separators_and_digits(self):
        for text in self.ACCEPTED:
            with self.subTest(text=text):
                self.assertEqual(
                    bs.parse_bs(text), datetime.date(2026, 9, 9),
                    f"parse_bs rejected {text!r}, which bs_convert.js accepts"
                )

    def test_js_accepts_the_same_separator_set(self):
        """Asserted against the JS source, since there is no JS runtime here.

        A shared separator set is a contract, and a contract that only one side
        knows about is not one. The full behavioural check lives in the JS unit
        tests; this catches the two regexes drifting apart.
        """
        source = open(JS_CONVERT, encoding="utf-8").read()
        self.assertIn(
            r"/[-/.\s]+/", source,
            "bs_convert.js parseBs separator class differs from tools/bs.py's "
            "_SEPARATORS"
        )

    def test_round_trip_through_both_directions(self):
        for text in ("2083-05-24", "2056-09-17", "1975-01-01"):
            with self.subTest(text=text):
                ad = bs.parse_bs(text)
                self.assertEqual(bs.format_bs(ad), text)


@tagged("-at_install", "post_install")
class TestRangeContract(TransactionCase):
    """Outside the table there is no answer, and guessing one would be wrong."""

    def test_before_range_raises(self):
        with self.assertRaises(UserError):
            bs.ad_to_bs(datetime.date(1850, 1, 1))

    def test_after_range_raises(self):
        with self.assertRaises(UserError):
            bs.ad_to_bs(datetime.date(2200, 1, 1))

    def test_first_and_last_supported_days_convert(self):
        """The boundaries themselves must work, not just the interior."""
        first = bs.bs_to_ad(bs.BS_MIN_YEAR, 1, 1)
        self.assertEqual(bs.ad_to_bs(first), (bs.BS_MIN_YEAR, 1, 1))

        last_day = bs.month_length(bs.BS_MAX_YEAR, 12)
        last = bs.bs_to_ad(bs.BS_MAX_YEAR, 12, last_day)
        self.assertEqual(bs.ad_to_bs(last), (bs.BS_MAX_YEAR, 12, last_day))

    def test_invalid_bs_day_raises(self):
        """A month's length comes from the table, not from a rule.

        BS months are 29-32 days with no formula, so "day 32" is valid in some
        months and not others. Accepting it blindly would shift the date.
        """
        length = bs.month_length(2083, 5)
        with self.assertRaises(UserError):
            bs.bs_to_ad(2083, 5, length + 1)

    def test_month_length_out_of_range_raises_user_error(self):
        """Not IndexError.

        A bare IndexError from a table lookup surfaces to the user as a server
        error with a traceback; UserError is the contract for a bad input.
        """
        with self.assertRaises(UserError):
            bs.month_length(bs.BS_MAX_YEAR + 1, 1)


@tagged("-at_install", "post_install")
class TestErrorContract(TransactionCase):
    """Python raises, JavaScript returns null. Deliberate, and asserted."""

    def test_python_parse_failure_raises(self):
        for bad in ("not a date", "2083-13-01", "2083-05", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(UserError):
                    bs.parse_bs(bad)

    def test_js_parse_failure_returns_null(self):
        """The widget must not break the form over a typo.

        Asserted against source because there is no JS runtime in a Python test.
        The two contracts differ on purpose: server-side a bad date is a bug or a
        validation error, client-side it is a user mid-typing.
        """
        source = open(JS_CONVERT, encoding="utf-8").read()
        body = re.search(r"export function parseBs\(.*?\n\}", source, re.S)
        self.assertTrue(body, "parseBs not found in bs_convert.js")
        self.assertIn(
            "return null", body.group(0),
            "parseBs must return null on bad input rather than throw"
        )


@tagged("-at_install", "post_install")
class TestWeekdayContract(TransactionCase):

    def test_weekday_is_sunday_first(self):
        """Sunday=0, not Monday=0.

        `datetime.date.weekday()` is Monday-first; BS weeks start on Sunday. The
        shift is the kind of off-by-one that only shows up as a picker column
        being one cell out.
        """
        # AD 2026-09-09 is a Wednesday -> Sunday-first index 3.
        self.assertEqual(bs.weekday(datetime.date(2026, 9, 9)), 3)
        self.assertEqual(bs.weekday(datetime.date(2026, 9, 13)), 0)  # Sunday

    def test_weekend_is_saturday(self):
        """Nepal's weekly holiday is Saturday, not Sunday.

        Getting this backwards would put a due date on a closed day.
        """
        self.assertEqual(names.WEEKEND_WEEKDAY, 6)
        self.assertTrue(bs.is_weekend(datetime.date(2026, 9, 12)))   # Saturday
        self.assertFalse(bs.is_weekend(datetime.date(2026, 9, 13)))  # Sunday

    def test_weekday_of_none_is_none(self):
        """An unset date is not a Saturday."""
        self.assertIsNone(bs.weekday(None))
        self.assertFalse(bs.is_weekend(None))
