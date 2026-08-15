# Bikram Sambat

The architecture reference for BS date display. Findings by ID in [`BACKLOG.md`](BACKLOG.md).

> **This file was an audit assessment and is now the design document.** The conversion-correctness
> evidence below is unchanged and still holds. Everything from "Root cause" onward replaces the
> earlier text, which described a mechanism that has since been built and then corrected.

## Conversion correctness — proven, not asserted

Every one of the **46,022 supported days** was replayed in both directions against
`nepali_datetime` 1.0.8.5 with **zero divergence**, and the fiscal-year arithmetic is exact and
contiguous across 125 BS years. The sweep is no longer a script nobody runs: it executes in the
test suite (`tests/test_conversion_contract.py`) in 0.9s, and it parses the *generated*
`bs_calendar_data.js` rather than the generator, so a stale checked-in table fails the build.

Supported range: **BS 1975-01-01 … 2100-12-30** (AD 1918-04-13 … 2044-04-12). Outside it the
conversion raises rather than guessing — the month-length table *is* the algorithm, and there is no
formula to extrapolate. Display falls back to Gregorian rather than showing nothing.

## Root cause of the list-view defect

Odoo 19 renders a user-facing date by **two** routes, and only one of them was covered.

| Route | Used by | Registry |
|---|---|---|
| A real Owl component | Form views always; a list column **only** when the arch sets an explicit `widget=` | `fields` |
| A plain formatted string, no component | **Readonly list cells**, kanban cards, column aggregates | `formatters` |

`list_renderer.xml:299-300` is the branch:

```xml
<t t-if="canUseFormatter(column, record)" t-out="getFormattedValue(column, record)"/>
<Field t-else="" name="column.name" .../>
```

`canUseFormatter` (`list_renderer.js:501-511`) returns `true` for any column without a `widget=` on a
row that is not being edited, and `getFormattedValue` resolves through `views/utils.js:139-151` to
`registry.category("formatters").get(field.type)`. Kanban does the same at
`kanban_record.js:216-219`.

The module overrode only the `fields` registry. So an invoice list — whose arch is plain
`<field name="invoice_date"/>` — never instantiated the dispatcher and kept rendering Gregorian,
while the same field in the form view rendered BS.

> **The premise that caused it, recorded rather than quietly amended.** The module's own source
> comment asserted that the `formatters` registry "is used for list *aggregates*" and that its call
> site "passes no field metadata", concluding that overriding it "would buy nothing". Both halves
> were wrong: it is the primary readonly-cell path, and `views/utils.js:146-147` passes `data` and
> `field`. The comment was confident, specific, cited a line number — and wrong.

**A second, independent gap**: the invoice/bill **Due Date** column is
`<field name="invoice_date_due" widget="remaining_days"/>` (`account/views/account_move_views.xml:536`).
An explicit `widget=` sends it down the component route, but the component it resolves is
`remaining_days`, not one of the three date widgets — and that component imports `formatDate`
**statically** (`remaining_days_field.js:9`, used at `:61`), so no registry entry reaches it either.
It was invisible to both mechanisms.

### Why the tests did not catch it

The only list-view test asserted `expect(".o_data_row").toHaveCount(1)` and nothing about the
rendered text. It stayed green while every list cell rendered Gregorian. Counting rows proves the
view did not crash; it proves nothing about the feature.

## Architecture

```
PostgreSQL (canonical Gregorian date / UTC timestamp)
        │
        ▼
   Odoo ORM  ── domains, sorting, grouping, arithmetic: all untouched
        │
        ▼
 effective calendar = user → company → 'ad'
        │
        ├── fields registry     → CalendarAwareDateField → BSDateField | native   (forms, widget= columns)
        ├── formatters registry → BS string | native formatter                    (list cells, kanban, aggregates)
        ├── parsers registry    → BS input accepted, AD and +1w still work        (typed input, search bar)
        ├── remaining_days patch→ BS for the absolute date only                   (Due Date column)
        └── ir.qweb.field.date/.datetime → company bs_report_output               (printed documents)
```

Nothing above the ORM line changes. There is exactly one conversion implementation, shared:
`tools/bs.py` (Python) and `static/src/bs_convert.js` (JavaScript), both fed from `tools/names.py`
via a generated table, with a test asserting the two agree.

## Effective-calendar precedence

**`res.users.calendar_system` → `res.company.calendar_system` → `'ad'`**, resolved once in
`models/res_users.py:80-92` (`_resolve_calendar_system`). There is no second preference system.

- The user field is empty by default, meaning "follow the company".
- Company default is `'ad'`, so installing the module changes nothing until someone opts in.
- The resolved value rides in `env.context` via `context_get()` for server-side consumers, and
  reaches the browser as a top-level `session_info` key (`models/ir_http.py:18-22`).
- `calendar_system` is in `_get_invalidation_fields()`, so a change takes effect on the next
  request rather than the next server restart.

Language and calendar are independent: **English + BS** and **Nepali + AD** are both valid.

Printed documents deliberately follow the **company** `bs_report_output` (`ad` / `bs` / `both`), not
the reader's own preference — an invoice must not change depending on who pressed Print.

## Storage strategy

**Bikram Sambat is presentation only.** `fields.Date` stays a Gregorian `date` column and
`fields.Datetime` stays a naive-UTC `timestamp`. No BS string is ever written, and no BS value ever
reaches a domain.

This is asserted, not assumed. `tests/test_calendar_preference.py::TestStorageInvariance` writes the
same date as a BS user and an AD user and compares the **raw SQL column**, because an ORM-level
assertion would still pass if a converter were rewriting values symmetrically on read and write. It
also asserts that a Gregorian domain still matches, that the BS equivalent does **not**, and that
`export_data` returns the Gregorian value.

Consequences that follow for free, and are therefore not at risk: sorting is `ORDER BY` on a real
date column, grouping is `date_trunc`, filtering is a domain over ISO strings, and every accounting
calculation — periods, lock dates, due dates, ageing, reconciliation — operates on the stored value.

## Date versus Datetime

Handled separately, deliberately.

| | `date` | `datetime` |
|---|---|---|
| Stored | Gregorian calendar date | naive UTC timestamp |
| Timezone | **none applied** — a date has no instant, so re-zoning it would invent one and shift the day west of UTC | UTC → `user.tz` → local Y/M/D → BS |
| Time shown | n/a | preserved, from the same user-zoned value the date came from |

**Never convert before normalising the timezone.** Core formats a datetime with
`value.setZone(options.tz || "default")` (`core/l10n/dates.js:434`), and `"default"` is the
**browser** zone, because Odoo never assigns `luxon.Settings.defaultZone` in production. Deriving a
BS day from that is wrong for the 5h45m before midnight in Kathmandu.

The discriminating case, asserted at every layer: **2026-09-08 18:30 UTC** is BS **2083-05-24** in
`Asia/Kathmandu` and **2083-05-23** in UTC. Both are correct for their reader, and a test that gets
the same answer for both is broken.

## Numerals

One company setting, `bs_digits`: `latin` (`2083-05-24`, the default) or `devanagari`
(`२०८३-०५-२४`). Neither is hard-coded anywhere; the JavaScript reads `session.bs_digits` and the
Python reads `company.bs_digits`. Devanagari is opt-in because it is the larger change to an
existing ledger, and because Latin digits tie back to a bank statement more easily.

Odoo cannot supply these: its `NUMBERING_SYSTEMS` table explicitly comments out `ne`
(`localization_service.js:21-31`), so the digits come from `tools/names.py`.

## Supported surfaces

| Surface | Status |
|---|---|
| Form views, `date` and `datetime` | **BS** |
| **List/tree cells** (invoice date, accounting date, bills, journal entries, payments, partners) | **BS** — the fix |
| **Due Date** (`remaining_days`) | **BS** for the absolute date; relative labels unchanged, see below |
| Kanban cards | **BS** |
| Column and group aggregates | **BS** |
| Typed input, including the search bar | BS accepted; AD and `+1w`/`today` still work |
| Printed documents (QWeb/PDF) | **BS**, per company `bs_report_output` |
| Standalone Nepali calendar browser | BS |
| Exports (CSV/XLSX) | **Gregorian, deliberately** |

## Intentional exceptions

Stated so they are not mistaken for oversights.

**Relative labels stay relative.** `remaining_days` shows "Today", "In 5 days", "Yesterday" for
anything within 99 days (`remaining_days_field.js:42-57`) and only falls back to an absolute date
beyond that. Those labels are calendar-neutral — "in 5 days" is the same statement in either
calendar — and they carry the at-a-glance overdue signal an accountant actually reads. Only the
absolute date underneath is converted.

**Exclusions on the formatter route are by field name only.** `getFormattedValue` passes the field
descriptor but not the record, so there is no model to match on. `create_date`, `write_date`,
`nextcall`, `lastcall` and the other technical names stay Gregorian everywhere — that is the
overwhelming majority, and they are the columns people actually see. The three model-scoped pairs
(`mail.message/date`, `mail.tracking.value/create_date`, `mail.notification/read_date`) keep their
exclusion on the component route only.

**Search filters and group-by still use Gregorian period boundaries.** A BS month is split across
two Gregorian buckets. This is the largest remaining functional gap and is tracked as **BSF-1** /
**BSF-3**; it needs either declarative BS-month filters or a stored `bs_year_month` column, because
BS months are 29–32 days from a lookup table and are not expressible as the `relativedelta` the
granularity registry requires.

**The calendar view grid keeps Gregorian month boundaries.** Use the standalone Nepali Calendar
action to browse a true BS month.

**Pivot cells and the calendar popover** have their own private `getFormattedValue`
(`pivot_renderer.js:90`, `calendar_common_popover.js:71`) and remain Gregorian. Pivot's real BS
problem is bucket boundaries, which is BSF-3.

**Exports stay Gregorian.** `Datetime.convert_to_export` calls `convert_to_display_name`
(`fields_temporal.py:287-294`), so converting there would silently break every re-import.

## Testing coverage

| Area | Where |
|---|---|
| 46,022-day sweep, both directions, month boundaries | `tests/test_conversion_contract.py` |
| Python/JS contract: digits, separators, padding, weekday forms, error semantics | same, plus `static/tests/bs_convert.test.js` |
| Preference precedence, cache invalidation, self-service rights | `tests/test_calendar_preference.py` |
| **Storage invariance via raw SQL**, domain behaviour, export | same |
| Timezone matrix, server side | `tests/test_timezone_and_reports.py` |
| Report output modes, per-field override, reader-independence | same |
| Dispatcher selection, component route | `static/tests/registry_overrides.test.js` |
| **Readonly list cells** — BS rendering, no component mounted, timezone, exclusions, digits, AD no-regression, out-of-range fallback | same |

Deliberately shared fixtures: the JavaScript and Python suites assert the **same dates**, so they
cross-check one contract rather than testing two things that each happen to pass.

## Upgrade considerations

This is the first alternate-calendar layer in this codebase — Odoo 19 has no alternate-calendar
support anywhere, Babel has no calendar parameter, and Intl's `ca-` extension has no Bikram Sambat
value. Every seam is our maintenance burden.

Per-major smoke test, in order of fragility:

1. **`canUseFormatter` / the list branch** (`list_renderer.xml:299`). If Odoo changes when a cell
   uses a component, list views silently revert to Gregorian. This is the seam that already failed
   once.
2. **The `remaining_days` patch.** A patched getter on a core component; if the getter is renamed or
   the widget is replaced, the Due Date column reverts.
3. **The `fields`/`formatters`/`parsers` registry keys.** A rename leaves Gregorian in place, which
   is the correct failure mode: English dates are cosmetic, wrong dates are not.
4. **`session_info`** and `_get_invalidation_fields`.
5. **`ir.qweb.field.*` converters** — `.date` delegates to `tools.format_date` while `.datetime`
   calls Babel directly, so both need overriding independently.

Two seams have failed during development, which is the best available evidence of how they fail:
silently, with dates still rendering, just in the wrong calendar. Any smoke test must therefore
assert the **rendered text**, never that a view merely mounted.
