# -*- coding: utf-8 -*-
"""Bikram Sambat <-> Gregorian conversion helpers.

Thin wrapper over the ``nepali-datetime`` package, which ships the vetted
month-length table (BS 1975..2100). Everything here is pure presentation:
Odoo continues to store Gregorian dates.

    >>> import datetime
    >>> from odoo.addons.l10n_np_bs.tools import bs
    >>> bs.ad_to_bs(datetime.date(2026, 9, 9))
    (2083, 5, 24)
    >>> bs.bs_to_ad(2083, 5, 24)
    datetime.date(2026, 9, 9)
    >>> bs.format_bs(datetime.date(2026, 9, 9), np_digits=True)
    '२०८३-०५-२४'
"""
import datetime

from odoo.exceptions import UserError
from odoo.tools.translate import _

try:
    import nepali_datetime
except ImportError:  # pragma: no cover
    nepali_datetime = None

# Devanagari digits, for display only
NP_DIGITS = "०१२३४५६७८९"

# Nepali month names (index 1..12)
MONTHS_NE = [
    None, "बैशाख", "जेठ", "असार", "साउन", "भदौ", "असोज",
    "कार्तिक", "मंसिर", "पुष", "माघ", "फागुन", "चैत",
]
MONTHS_EN = [
    None, "Baisakh", "Jestha", "Ashar", "Shrawan", "Bhadra", "Asoj",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
]
# Nepali weekday names, Sunday first (BS weeks start on Sunday)
WEEKDAYS_NE = ["आइतबार", "सोमबार", "मंगलबार", "बुधबार",
               "बिहिबार", "शुक्रबार", "शनिबार"]


def _require_lib():
    if nepali_datetime is None:
        raise UserError(_(
            "The 'nepali_datetime' Python package is required for the Nepali "
            "calendar. Install it with: pip install nepali-datetime"
        ))


def to_np_digits(text):
    """Render ASCII digits in the string as Devanagari digits."""
    return "".join(NP_DIGITS[int(c)] if c.isdigit() else c for c in str(text))


def from_np_digits(text):
    """Inverse of :func:`to_np_digits`."""
    out = []
    for ch in str(text):
        idx = NP_DIGITS.find(ch)
        out.append(str(idx) if idx >= 0 else ch)
    return "".join(out)


def ad_to_bs(value):
    """Gregorian date/datetime -> ``(bs_year, bs_month, bs_day)``."""
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
            "(BS 1975-01-01 to 2100-12-30). Underlying error: %(err)s",
            date=value, err=exc,
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
    :param np_digits: render digits in Devanagari
    :param month_names: substitute the Nepali month name for ``%m``
    """
    if value is None:
        return ""
    y, m, d = ad_to_bs(value)
    out = (fmt.replace("%Y", f"{y:04d}")
              .replace("%m", MONTHS_NE[m] if month_names else f"{m:02d}")
              .replace("%d", f"{d:02d}"))
    return to_np_digits(out) if np_digits else out


def parse_bs(text):
    """Parse ``2083-05-24`` (ASCII or Devanagari digits) -> Gregorian date."""
    parts = from_np_digits(str(text).strip()).replace("/", "-").split("-")
    if len(parts) != 3:
        raise UserError(_("Expected a Bikram Sambat date as YYYY-MM-DD, got %s", text))
    return bs_to_ad(*parts)


def month_length(year, month):
    """Number of days in the given BS month."""
    _require_lib()
    return nepali_datetime._days_in_month(int(year), int(month))  # noqa: SLF001
