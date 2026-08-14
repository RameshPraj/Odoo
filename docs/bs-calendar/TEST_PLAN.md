# Test plan

Baseline: **121 tests** across the eight custom modules, all green. Any new failure is a regression,
never a rebaseline.

Two things about the original suite shaped this plan:
- **There were zero JavaScript tests.** `l10n_np_bs/static/tests/` was declared in the manifest and
  was an empty, untracked directory — so it did not even exist on a fresh clone. Every conversion,
  boundary and timezone concern lived in untested JS.
- **The 46,022-day cross-check existed and never ran.** Wiring it in was the first test task.

## Status — what is implemented, as measured

`nepali_calendar_core`, run as
`-u nepali_calendar_core --test-enable --test-tags /nepali_calendar_core`:

**115 tests, 0 failed, 0 errors** (77 post-install, including **19 JavaScript** tests executed in
headless Chrome).

| § | Area | File | State |
|---|---|---|---|
| 1 | Conversion contract | `tests/test_conversion_contract.py` | **Done.** The 46,022-day sweep now runs (0.9s, so no sampling); name tables asserted byte-equal to `tools/names.py`; format, parse, range and error contracts pinned across both layers |
| 2 | Timezone | `tests/test_timezone_and_reports.py` | **Done, server-side.** Kathmandu / UTC / New York on the discriminating instant, local-midnight boundary, and `date`-is-not-shifted. The *widget's* timezone behaviour is covered by code but not yet by a test — see gaps |
| 3 | Preference | `tests/test_calendar_preference.py` | **Done,** including cache invalidation and self-service rights |
| 4 | ORM invariance | `tests/test_calendar_preference.py` | **Done** via raw SQL on `res_currency_rate.name`, plus domain and `export_data` |
| 5 | Reports | `tests/test_timezone_and_reports.py` | **Done** for all three output modes, the per-field `calendar` override, digits, and reader-independence |
| 9 | JavaScript | `static/tests/*.test.js`, run by `tests/test_js_unit.py` | **31 tests**, executed in headless Chrome: `bs_convert` (19) and `registry_overrides` (12) |

Two things worth recording about how this was reached, because both were wrong in the original plan:

- The `formatters` registry override was **dropped**, not deferred — it could not have worked. See
  the correction in `02_ARCHITECTURE.md`.
- `_prepare_environment` was asserted to contain a core `format_date` to prove we do not shadow it.
  **Core does not define `format_date` in the QWeb environment at all** — `mail.render.mixin` and the
  EDI modules each inject their own. The assertion now checks that the name stays free, which is the
  actual requirement.

### Two bugs these tests found in the tests themselves

Recorded because both were the failure mode where a test reports success while
proving nothing, which is worse than a red build:

1. **Assertions read `textContent` for a value living in `input.value`.** Every negative assertion
   (`not.toInclude("2083-…")`) was comparing against the empty string and passing. Fixed by reading
   input values, and each negative is now preceded by a **positive** assertion so it cannot pass over
   an empty render.
2. **A preference test wrote `NULL` over a `NOT NULL` column.** The AD-fallback test was asserting a
   state PostgreSQL forbids. The constraint is the stronger guarantee, so it is now asserted directly
   and the fallback is exercised on in-memory records instead. See BSD-11.

A third, in shipped code rather than a test: `bs_date_field.js`'s `extractProps` still defaulted
`npDigits` to `true` while `defaultProps`, `formatBs` and `tools/bs.py` had all been moved to Latin —
so an explicit `widget="bs_date"` rendered Devanagari and every other route rendered ASCII. It now
falls back to the company setting.

### Not yet covered, and not to be mistaken for covered

- **The dispatcher's *selection*.** Its two halves are each tested — the exclusion predicate directly
  (6 tests), and BS rendering through `widget="bs_date"` (4 tests, including the timezone matrix) —
  but not their composition: that with `session.calendar_system === "bs"` a bare
  `<field name="invoice_date"/>` picks `BSDateField` while `create_date` does not. The override runs
  once at module import, so a test cannot re-key it, and mutating the global `fields` registry from a
  test would leak into every later suite. Closing it means exporting an idempotent
  `install(calendar)`, which is a refactor of shipped code. **BSD-9.**
- **`bs_date_field` interaction** — type-and-commit, picker click, rejected input. Rendering and
  timezone are now covered; behaviour is not. **BSD-10.**
- §6 Accounting Nepal regression, §7 security, §8 SaaS isolation — all still pending.

## 1. Conversion

| Test | Assertion |
|---|---|
| Exhaustive sweep | `tools/selftest.py` wired in: all 46,022 days, AD→BS and BS→AD, 0 mismatches. **Refactor `main()` into `check() -> list[mismatch]`** — it currently `sys.exit`s and `print`s, so it cannot be called from a `TestCase` |
| Generator drift | The checked-in `bs_calendar_data.js` still matches what the current `nepali_datetime` CSV would produce. Nothing asserts this today |
| Round trips | `AD → BS → AD == AD` and `BS → AD → BS == BS` across the range |
| **Range ends** | BS 1975-01-01, BS 2100-12-30, AD 1918-04-13, AD 2044-04-12 all convert; one day beyond each raises. Only the **low** side is tested today |
| **Month lengths** | Explicit assertions for a 29-, 30-, 31- **and 32**-day month. The current stride test crosses them incidentally and asserts none |
| **`month_length()`** | Tested at all — it is the function whose missing guard causes the fiscal-year traceback |
| Invalid input | month 13, day 33, two parts, bad separators — raise on Python, `null` on JS |
| Python ↔ JS parity | Same input, same output, for format and parse, per the reconciled contract |

## 2. Timezone — the 94-field risk

The highest-value new tests, because this is what the global rollout exposes.

| Case | Assertion |
|---|---|
| Datetime near midnight | A value at **23:30** and **00:15** Asia/Kathmandu renders the **same BS day** for a Kathmandu user regardless of browser timezone |
| Timezone matrix | The same stored UTC datetime, read by users in `Asia/Kathmandu`, `UTC`, `America/New_York`, `Asia/Kolkata` → each sees the BS date correct **for their own tz** |
| The known failure | `2026-09-08 19:00 UTC` → BS 2083-05-24 for a Kathmandu user. Today this returns 2083-05-23 on a UTC browser |
| Date vs Datetime | A `date` field is **not** tz-shifted; a `datetime` field is. Asserted separately |
| "Today" | The widget's today-highlight agrees with the server's `context_today` for a user in `Asia/Kathmandu` when the server clock is 18:30 UTC |
| Write-back | Picking a BS date on a datetime field stores the correct UTC instant, not browser-local midnight |

## 3. Preference

| Case | Expected |
|---|---|
| User `bs`, company `ad` | BS |
| User unset, company `bs` | BS |
| User `ad`, company `bs` | AD — the user overrides |
| Neither set | AD |
| Switching AD → BS → AD | Display flips; **stored values unchanged** |
| Non-admin sets their own | Succeeds without elevated rights (proves `SELF_WRITEABLE_FIELDS`) |
| **Invalidation** | Changing the preference takes effect on the next request — proves `_get_invalidation_fields`. Without it the `ormcache('self.env.uid')` on `context_get` stays stale until restart |
| Digit style | `latin` and `devanagari` both render; the setting is honoured by the widget, the calendar action **and** reports — all three currently ignore it |

## 4. ORM invariance — the core guarantee

The test that proves BS never touches storage:

```
create the same invoice as a BS user and as an AD user
→ assert the raw PostgreSQL date/timestamp columns are IDENTICAL
```

Read the column with raw SQL, not through the ORM, so no conversion can hide a difference. Repeat for
`account.move`, `stock.picking` (datetime) and `l10n_np.loan`.

Plus: domains, `search`, `read`, `export_data` and RPC all return canonical AD; no BS string can
reach a domain.

## 5. Reports

| Case | Assertion |
|---|---|
| `ir.qweb.field.date` | Renders BS for a BS user, AD for an AD user |
| `ir.qweb.field.datetime` | Same — **tested separately**, because it calls Babel directly rather than `tools.format_date` |
| Output modes | `ad`, `bs`, `both` each render as specified |
| **Export is untouched** | A CSV/XLSX export by a BS user is byte-identical to an AD user's. This is the guard against the `convert_to_export` → `convert_to_display_name` trap |
| Round trip | Export as BS user → re-import → records unchanged |
| Mail templates | Existing templates unchanged; `format_date_bs` available as a **new** key |

## 6. Accounting Nepal regression

The 16 existing BS-date tests, re-pointed at core, plus:

- Migration on a database **with the group set** → company default becomes `bs`, users keep seeing BS
- Migration where a user was explicitly removed from the group → that user gets `ad`
- VAT return, TDS certificate, loan schedule figures byte-identical before and after
- Fiscal-year generation unaffected
- A BS-mode user still cannot post into a locked period

## 7. Security

| Case | Assertion |
|---|---|
| Preference grants no access | A BS user sees exactly the records an AD user sees — same ACLs, same record rules, same company boundary |
| No `sudo()` | The preference is read without elevation; `SELF_READABLE_FIELDS` is what makes it work |
| **View-cache isolation** | Two users with different preferences, hitting the same view — neither is served the other's rendering. This is the trap that `_get_view_cache` (no uid in its default key) creates; the registry route avoids it, and the test proves it stays avoided |
| No injection | BS input cannot construct a domain; domains are built from ISO strings only |

## 8. SaaS isolation

Two databases, opposite company defaults (`db_a` = BS, `db_b` = AD):

- A user in `db_a` sees BS; a user in `db_b` sees AD — no bleed
- Switching the preference in `db_a` does not affect `db_b`
- No filesystem or process-global state carries the preference

## 9. JavaScript — from zero

| Suite | Covers |
|---|---|
| `bs_convert` | conversion vectors matching the Python tests exactly, boundaries, invalid input, `parseBs` returning `null` |
| `bs_date_field` | render, type-and-commit, picker selection, rejected input, **timezone cases from §2** |
| registry override | the native `date`/`datetime` widget is replaced when the preference is BS, and **not** when it is AD |
| exclusions | `create_date` renders AD even for a BS user |

Populating the empty declared bundle is a prerequisite for calling any JS behaviour tested.

## Execution order

Each stage must be green before the next begins.

1. Baseline: 121 tests green
2. Selftest wired in (§1) — before any code moves
3. Conversion contract tests (§1) after the Python/JS reconciliation
4. **Timezone (§2) — before the registry override lands**
5. Preference (§3)
6. ORM invariance (§4) as soon as the override is on
7. Accounting Nepal regression (§6)
8. Reports (§5)
9. Security (§7) and SaaS (§8)
10. JS suite (§9)

## Coverage gaps this plan does not close

Named so they are not mistaken for covered:

- **Search filters and group-by** — deferred; the acceptance test is "a BS month selects only that BS
  month", which fails today and will continue to
- **Calendar month grid** — labels only; boundaries stay Gregorian
- **POS UI** — a separate frontend bundle, untested and uncovered
- **PDF rendering end to end** — `wkhtmltopdf` is not installed, so report tests assert the QWeb
  **HTML**, not the final PDF
