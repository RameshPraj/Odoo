# -*- coding: utf-8 -*-
"""Bikram Sambat <-> Gregorian conversion.

A thin wrapper over the ``nepali-datetime`` package, which ships the vetted
month-length table (BS 1975..2100). Everything here is presentation: Odoo stores
canonical Gregorian dates and this module never changes that.

    >>> import datetime
    >>> from odoo.addons.nepali_calendar_core.tools import bs
    >>> bs.ad_to_bs(datetime.date(2026, 9, 9))
    (2083, 5, 24)
    >>> bs.bs_to_ad(2083, 5, 24)
    datetime.date(2026, 9, 9)
    >>> bs.format_bs(datetime.date(2026, 9, 9), np_digits=True)
    '२०८३-०५-२४'

Contract, deliberately symmetric with ``static/src/bs_convert.js``:

* ``np_digits`` / ``npDigits`` default to **False** on both sides. Devanagari is
  opt-in, because it is the larger change to an existing ledger.
* Parsing accepts ``-``, ``/``, ``.`` and whitespace on both sides. Being liberal
  on input is right; only the *output* format is canonical.
* Python **raises** ``UserError``; JavaScript **returns null**. This asymmetry is
  intentional and documented: server-side a bad date is a bug or a validation
  error, whereas the widget must show a notification rather than break the UI.
* Month and weekday names come from ``tools/names.py``, which is also what
  ``gen_js_data.py`` emits into the JS table. One source, three consumers.
"""
import datetime
import re

from odoo.exceptions import UserError
from odoo.tools.translate import _

try:
    import nepali_datetime
except ImportError:  # pragma: no cover
    nepali_datetime = None

#: Supported range. Exported so callers and error messages agree, rather than
#: repeating the bounds as prose (the JS side exports the same two constants).
BS_MIN_YEAR = 1975
BS_MAX_YEAR = 2100

# Names live in tools/names.py, which gen_js_data.py also reads when it emits the
# JS table, so the browser and the server cannot carry different spellings.
# Re-exported here so that `bs.MONTHS_NE` keeps working for existing callers.
from .names import (  # noqa: F401  (deliberate re-export)
    MONTHS_EN,
    MONTHS_NE,
    NP_DIGITS,
    WEEKDAYS_NE_LONG,
    WEEKDAYS_NE_SHORT,
    WEEKEND_WEEKDAY,
)

# Accepted separators on parse. Matches bs_convert.js's parseBs.
_SEPARATORS = re.compile(r"[-/.\s]+")


def _require_lib():
    if nepali_datetime is None:
        raise UserError(_(
            "The 'nepali_datetime' Python package is required for the Nepali "
            "calendar. Install it with: pip install nepali-datetime"
        ))


def to_np_digits(text):
    """Render ASCII digits in the string as Devanagari digits."""
    out = []
    for ch in str(text):
        # `str.isdigit()` is True for characters int() rejects, e.g. superscripts.
        out.append(NP_DIGITS[int(ch)] if ch in "0123456789" else ch)
    return "".join(out)


def from_np_digits(text):
    """Inverse of :func:`to_np_digits`."""
    out = []
    for ch in str(text):
        idx = NP_DIGITS.find(ch)
        out.append(str(idx) if idx >= 0 else ch)
    return "".join(out)


def ad_to_bs(value):
    """Gregorian date/datetime -> ``(bs_year, bs_month, bs_day)``.

    A ``datetime`` is narrowed to its date. **The caller is responsible for
    having already converted UTC to the user's timezone** -- see
    :func:`~odoo.addons.nepali_calendar_core.models.res_users.ResUsers` and
    ``fields.Datetime.context_timestamp``. Converting a UTC datetime directly
    yields the wrong BS day for part of every day.
    """
    _require_lib()
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        value = value.date()
    try:
        d = nepali_datetime.date.from_datetime_date(value)
    except Exception as exc:
        raise UserError(_(
            "%(date)s is outside the supported Bikram Sambat range "
            "(BS %(lo)s-01-01 to %(hi)s-12-30). Underlying error: %(err)s",
            date=value, lo=BS_MIN_YEAR, hi=BS_MAX_YEAR, err=exc,
        )) from exc
    return (d.year, d.month, d.day)


def bs_to_ad(year, month, day):
    """``(bs_year, bs_month, bs_day)`` -> Gregorian ``datetime.date``."""
    _require_lib()
    try:
        return nepali_datetime.date(int(year), int(month), int(day)).to_datetime_date()
    except Exception as exc:
        raise UserError(_(
            "%(y)s-%(m)s-%(d)s is not a valid Bikram Sambat date. "
            "Underlying error: %(err)s",
            y=year, m=month, d=day, err=exc,
        )) from exc


def format_bs(value, fmt="%Y-%m-%d", np_digits=False, month_names=False):
    """Format a Gregorian date as Bikram Sambat.

    :param fmt: ``%Y`` ``%m`` ``%d`` placeholders
    :param np_digits: render digits in Devanagari (default ASCII, matching JS)
    :param month_names: substitute the Nepali month name for ``%m``
    """
    if value is None:
        return ""
    y, m, d = ad_to_bs(value)
    if month_names:
        # Space-separated, matching bs_convert.js formatBs and normal Nepali use.
        out = f"{y:04d} {MONTHS_NE[m]} {d:02d}"
    else:
        out = (fmt.replace("%Y", f"{y:04d}")
                  .replace("%m", f"{m:02d}")
                  .replace("%d", f"{d:02d}"))
    return to_np_digits(out) if np_digits else out


def parse_bs(text):
    """Parse ``2083-05-24`` -> Gregorian date.

    Accepts ``-``, ``/``, ``.`` or whitespace separators, and ASCII or Devanagari
    digits. Raises ``UserError`` on anything else -- the JS twin returns ``null``
    instead, by design.
    """
    cleaned = from_np_digits(str(text).strip())
    parts = [p for p in _SEPARATORS.split(cleaned) if p]
    if len(parts) != 3:
        raise UserError(_(
            "Expected a Bikram Sambat date as YYYY-MM-DD, got %s", text))
    return bs_to_ad(*parts)


def month_length(year, month):
    """Number of days in the given BS month (29..32).

    Wraps the library's exceptions like every sibling here. It previously did
    not, so an out-of-range year surfaced as a raw ``KeyError`` that escaped
    callers catching ``UserError`` -- reachable by default from BS 2097, because
    the fiscal-year wizard offers ``current + 4``.
    """
    _require_lib()
    year, month = int(year), int(month)
    if not BS_MIN_YEAR <= year <= BS_MAX_YEAR:
        raise UserError(_(
            "BS year %(y)s is outside the supported range %(lo)s-%(hi)s.",
            y=year, lo=BS_MIN_YEAR, hi=BS_MAX_YEAR,
        ))
    if not 1 <= month <= 12:
        raise UserError(_("%s is not a valid Bikram Sambat month (1-12).", month))
    # Derived from public API, not `nepali_datetime._days_in_month` (COD-10).
    #
    # The private call worked, and the library is pinned
    # (`nepali-datetime==1.0.8.5`), so this was never load-bearing risk. But a
    # leading underscore is the author saying the name may change without notice,
    # and a pin is a decision somebody eventually revisits.
    #
    # The length is found by asking which day numbers the library will accept:
    # BS months run 29 to 32 days, and `date()` refuses an invalid one.
    #
    # The obvious derivation -- Gregorian of the 1st of this month subtracted
    # from the 1st of the next -- was written first and is **wrong at the top of
    # the range**. December of BS 2100 needs BS 2101-01-01, which the library
    # refuses, so `month_length(2100, 12)` would have raised where it used to
    # return 30. That year is in scope: BS_MAX_YEAR is 2100 and the docstring
    # above notes the fiscal-year wizard reaches BS 2097 by default. The first
    # verification missed it by sweeping MINYEAR+1..MAXYEAR-1, which excluded
    # precisely the boundary that broke.
    #
    # This form has no boundary case, and was checked against the private
    # function across the library's **entire** range: 1,512 months, zero
    # mismatches, BS 2100-12 included.
    try:
        for length in (32, 31, 30, 29):
            # ValueError, not Exception: it is the library's answer to "is this a
            # real day", verified as the type raised for an over-long day, an
            # invalid month and an out-of-range year alike. Catching broadly here
            # would swallow a genuine fault and return a wrong month length, which
            # is exactly the silent-wrong-date failure this module exists to
            # prevent.
            try:
                nepali_datetime.date(year, month, length)
            except ValueError:  # noqa: S112 - the exception IS the signal
                continue
            return length
        raise ValueError(f"no valid day count for BS {year}-{month}")
    except Exception as exc:
        raise UserError(_(
            "Could not determine the length of BS %(y)s-%(m)s. "
            "Underlying error: %(err)s", y=year, m=month, err=exc,
        )) from exc


def weekday(value):
    """Gregorian date -> weekday index, 0 = Sunday (BS convention)."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        value = value.date()
    # date.weekday() is Monday=0; shift to Sunday=0.
    return (value.weekday() + 1) % 7


def is_weekend(value):
    """True if the date falls on the Nepali weekly holiday (Saturday)."""
    wd = weekday(value)
    return wd is not None and wd == WEEKEND_WEEKDAY
