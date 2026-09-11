==========================
Nepal Bikram Sambat Dates
==========================

The user-facing half of the Bikram Sambat calendar: the date picker, the list and
form renderers, and the field widgets.

The conversion itself, and the single source of truth for it, live in
``nepali_calendar_core``. This module only presents what that one computes, so
there is exactly one implementation of the calendar arithmetic.

Nothing here changes how a date is stored. A BS-rendered list still sorts,
searches, groups and filters on the underlying Gregorian value, because the value
never changed -- only its rendering did.

Known gaps
==========

**TST-4**: the JavaScript in ``static/src/`` has no automated tests. The declared
test bundle directory is empty and untracked, so it does not exist on a fresh
clone.

See ``docs/bs-calendar/`` for the design and test plan, and **BS-20** in
``docs/project-review/BACKLOG.md`` for why list views needed separate treatment
from form views.
