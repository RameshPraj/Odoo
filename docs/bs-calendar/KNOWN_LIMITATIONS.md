# Known limitations

What BS support will **not** do after this pass, stated plainly so nobody discovers it in production.

## 1. Search, filters and group-by remain Gregorian

**The most consequential limitation.** A BS user filtering "August 2026" gets **BS Bhadra 16 – Ashoj
15** — every BS period is split.

Bucket boundaries are computed with luxon `startOf`/`endOf` in
`search/utils/dates.js:140-172`, and group-by boundaries in SQL via `date_trunc`
(`orm/models.py:2109`). BS months are 29–32 days from a lookup table, so they are **not expressible**
as the `relativedelta` the granularity registry requires, and PostgreSQL has no
`date_trunc('bs_month', …)`.

Practical effect: **dates display in BS right up until you report by period** — which is most of what
an accountant does. Design and backlog in [`SEARCH_AND_FILTERS.md`](SEARCH_AND_FILTERS.md);
recommended route is a stored `bs_year_month` column.

## 2. Group-by labels cannot be fixed from the frontend

Group headers are **server-produced** — `model/relational_model/utils.js:627-631` returns the label
the server already formatted, and pivot does the same (`pivot_model.js:928`). No JS change can alter
them.

Relabelling Gregorian buckets in BS is possible server-side, but **would be worse than not doing it**:
a group labelled "Bhadra" that actually contains Bhadra 16 – Ashoj 15 looks correct and is not. Only
ship labels together with correct boundaries.

## 3. The calendar month grid stays Gregorian

FullCalendar computes its own Gregorian month range. Toolbar titles, column headers and day-cell
numbers are patchable; the **month boundaries are not** without a custom FullCalendar view plugin.

So a BS user gets a Gregorian grid with BS labels — internally inconsistent. The standalone
**Nepali Calendar** client action (already in the repo) remains the way to browse a true BS month, and
that pattern should be kept rather than replaced.

## 4. The POS UI is not covered

Point of Sale renders in its own frontend bundle with its own components. Back-office POS records
(`pos.order`, `pos.session`) follow the preference; the **cashier-facing UI and printed receipts do
not**.

## 5. Exports stay Gregorian — by design

CSV and XLSX exports remain AD ISO, deliberately, because `Datetime.convert_to_export` internally
calls `convert_to_display_name` (`fields_temporal.py:287-294`). Making display BS by that route would
silently corrupt every export and break re-import round-trips.

If BS export is wanted, it must be an **additional** column, never a changed one.

## 6. Odoo's own `format_date` call sites are untouched

218 direct `tools.format_date` / `format_datetime` call sites exist across ~130 core files. They are
not funnelled, and roughly fifteen build **legal e-invoicing payloads** (`account_edi_ubl_cii`,
`l10n_es_edi_tbai`) that must stay Gregorian.

Only `t-field` / `t-out` output goes through the converter we override. A core feature that formats a
date in Python and puts it in a plain string — a dashboard subtitle, an activity summary, a chatter
message — will show AD.

## 7. `wkhtmltopdf` is not installed

Report tests assert the QWeb **HTML**. Final PDF rendering is unverified because the patched
`wkhtmltopdf` 0.12.6 build is absent from this environment.

## 8. Modules that are not installed are not covered

`project`, `hr_holidays`, `hr_attendance`, `hr_recruitment`, `maintenance` are **uninstalled**;
`hr_appraisal` is **uninstallable**. The brief asks for them.

The global mechanism means they would be covered automatically on install — but coverage is not the
same as verification, and no row in [`MODULE_COVERAGE.md`](MODULE_COVERAGE.md) may be marked *Tested*
without a test.

## 9. BS smart-date input is not supported

Odoo's relative-date DSL (`+1m`, `-2w`, `today`) uses Gregorian `relativedelta`
(`tools/date_utils.py:108+`), so a BS "+1 month" is not expressible. BS input must be an absolute
date.

## 10. Range limit: BS 1975 – 2100

Outside AD 1918-04-13 … 2044-04-12 conversion raises rather than guessing — the right behaviour, since
the table *is* the algorithm and there is no formula to extrapolate.

Two consequences: historical records before 1918 cannot display BS, and the fiscal-year wizard
approaches the upper bound from **BS 2097** onward because it defaults to `current + 4`.

## 11. No upstream contract to rely on

Odoo 19 has **no** alternate-calendar support anywhere — an exhaustive grep for
`hijri|jalali|buddhist|bikram|calendar_system` across core returns two false positives (an ACL id and
an emoji name). Babel has no calendar parameter; Intl's `ca-` extension has no Bikram Sambat value, so
luxon's `outputCalendar` — which looks like the obvious hook — cannot deliver BS.

**This is the first alternate-calendar layer in this codebase.** Every seam is our maintenance burden,
and each Odoo major upgrade needs a smoke test of: the three registry overrides, the widget's
`standardFieldProps` shape, `session_info`, and the `ir.qweb.field.*` converters.

## 12. Dependency fragility

`nepali_datetime` is unpinned, absent from `requirements.txt`, and we call a **private** symbol
(`_days_in_month`). A minor upstream change can break fiscal-year generation at runtime.

Mitigated, not eliminated: pinning it and wiring the 46,022-day selftest into CI means a library
change fails the build instead of silently producing wrong dates.
