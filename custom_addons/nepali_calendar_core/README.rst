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

Supported reporting and known boundaries
========================================

Printed QWeb dates can be configured per company as Gregorian only, Bikram
Sambat only, or both. The default both-date form is appropriate for accounting
documents: it keeps the Nepali-facing BS date while retaining the canonical AD
date used for reconciliation and audit.

The JavaScript unit suite and the exhaustive 46,022-day
``tools/selftest.py`` verification run as part of the automated test suite.
Exports, API payloads, search domains, and Gregorian group-by boundaries remain
Gregorian deliberately; changing those surfaces would break round trips or
change accounting/reporting semantics rather than merely add a display date.

See ``docs/bs-calendar/`` for the design, the coverage matrix and the test plan.
