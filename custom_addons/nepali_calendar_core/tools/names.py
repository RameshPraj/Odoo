# -*- coding: utf-8 -*-
"""Bikram Sambat month and weekday names -- the single source for all three layers.

These names previously existed in **three** places: ``bs.py``, the generated
``bs_calendar_data.js``, and hard-coded inside ``gen_js_data.py`` which was
supposed to be generating them. Three copies of a translation table is three
chances to disagree, and they had already begun to (Python carried long weekday
names, JS short ones).

They now live here, and:

* ``bs.py`` imports them,
* ``gen_js_data.py`` imports them and *emits* them into the JS table,

so the browser and the server cannot drift.

This module deliberately imports **nothing** -- not odoo, not nepali_datetime.
``gen_js_data.py`` is a standalone script run outside an Odoo process, and it must
be able to load this file directly by path.
"""

#: Devanagari digits, index 0..9. Display only; never parsed into storage.
NP_DIGITS = "०१२३४५६७८९"

#: Month names, **index 1..12** with a ``None`` at 0 so that ``MONTHS_NE[month]``
#: reads naturally against a 1-based BS month number.
MONTHS_NE = [
    None, "बैशाख", "जेठ", "असार", "साउन", "भदौ", "असोज",
    "कार्तिक", "मंसिर", "पुष", "माघ", "फागुन", "चैत",
]
MONTHS_EN = [
    None, "Baisakh", "Jestha", "Ashar", "Shrawan", "Bhadra", "Asoj",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
]

#: Sunday first -- Bikram Sambat weeks start on Sunday. Index 0..6, no ``None``
#: padding, because weekday indices are 0-based everywhere they come from
#: (``date.weekday()`` variants, ``Date.getUTCDay()``).
#:
#: Both lengths are kept: the date picker header needs the short form to fit a
#: seven-column grid, printed documents generally want the long one.
WEEKDAYS_NE_LONG = [
    "आइतबार", "सोमबार", "मंगलबार", "बुधबार", "बिहिबार", "शुक्रबार", "शनिबार",
]
WEEKDAYS_NE_SHORT = [
    "आइत", "सोम", "मंगल", "बुध", "बिहि", "शुक्र", "शनि",
]

#: Saturday, not Sunday, is the weekly holiday in Nepal. Index into the
#: Sunday-first lists above.
WEEKEND_WEEKDAY = 6
