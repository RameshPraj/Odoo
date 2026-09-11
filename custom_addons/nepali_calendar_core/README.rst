=====================
Nepali Calendar Core
=====================

Bikram Sambat rendering for Odoo 19, without touching how dates are stored.

Every date stays a PostgreSQL ``date``/``timestamp`` in the Gregorian calendar.
This module changes only the *presentation* layer, by overriding the field
formatters and QWeb converters that Odoo already routes every date through. That
is deliberate and non-negotiable: ORM domains, sorting, grouping, date arithmetic,
fiscal logic and every API keep working on the real stored value.

Two representations, one source of truth
========================================

* ``res.users.calendar_system`` and ``res.company`` decide what a given user sees.
* ``tools/bs.py`` holds the conversion, and ``tools/gen_js_data.py`` generates the
  JavaScript lookup table from it, so the Python and JavaScript sides cannot drift.
* ``tools/selftest.py`` cross-checks all 46,022 days both ways.

Known gaps
==========

The JavaScript has no automated tests (audit finding **TST-4**), and
``tools/selftest.py`` is not yet wired into the test suite (**BS-1**).

See ``docs/bs-calendar/`` for the design, the coverage matrix and the test plan.
