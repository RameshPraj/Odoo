=========================================
Nepal Fiscal Year (Shrawan to Ashar)
=========================================

Generates ``account.fiscal.year`` records on the Nepali fiscal calendar, which runs
from 1 Shrawan to the last day of Ashar -- roughly mid-July to mid-July, and *not*
a fixed Gregorian date.

Why the end date is computed, not fixed
=======================================

Ashar has 29, 30, 31 or 32 days depending on the year, so the Gregorian end date
moves. A test asserts exactly this, because hard-coding "15 July" is the obvious
mistake and it is wrong in most years.

The wizard is idempotent: by default it skips years that already exist, and
regenerates only when explicitly told to overwrite.

Relationship to ``account_fiscal_year``
=======================================

This module builds on the vendored OCA ``account_fiscal_year``, which is AGPL-3.
See ``custom_addons/VENDORED.md`` and audit finding **LIC-1** for what that means
for the combined work's licence.
