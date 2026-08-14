# 01 — Current state

What exists today, measured. Written before any implementation, so the design below rests on
evidence rather than assumption. Every claim cites `file:line`.

> **This is a "before" snapshot and is deliberately not updated.** It is the evidence the design was
> derived from, and rewriting it would destroy that. Several rows in the table below have since been
> addressed — the per-user preference, the timezone handling, report output, the JS test suite and the
> 46,022-day check all exist now. For what is true *currently*, read
> [`BACKLOG.md`](BACKLOG.md#in-this-pass--status) and
> [`TEST_PLAN.md`](TEST_PLAN.md#status--what-is-implemented-as-measured); the file paths here also
> now read `nepali_calendar_core/…` rather than `l10n_np_bs/…`.

## Summary

BS support exists and the **conversion mathematics is exact** — but it is an
Accounting-Nepal-specific feature, not a platform capability:

| | Today |
|---|---|
| Coverage | **20 fields across 14 models** — a hand-maintained allowlist |
| Total business date fields in this database | **237** (of 1,223 stored date/datetime fields) |
| Gate | a **security group**, granted database-wide from Settings |
| Per-user preference | **none** |
| Views covered | `form` and `list` only |
| Search / filters / group-by | **not covered** — every BS month is split by Gregorian buckets |
| Reports / PDF / exports | **not covered at all** — `format_bs` exists and is wired to nothing |
| `datetime` fields | claimed supported, **zero timezone handling**; latent only because no datetime field currently reaches the widget |
| JS unit tests | **zero** — the declared `static/tests/` directory is empty |
| The 46,022-day verification | exists in `tools/selftest.py`, **invoked by nothing** |

## What is measurably correct

Verified by execution against `nepali_datetime` 1.0.8.5, not by inspection:

- **AD→BS for every one of the 46,022 supported days: 0 mismatches.**
- **BS→AD for every day: 0 mismatches.**
- The generated JS table matches the library for all 1,512 (year, month) pairs.
- Epoch consistent: `BS_EPOCH_AD = [1918, 4, 13]` (`bs_calendar_data.js:15`).
- Range BS 1975–2100; all four month lengths (29/30/31/32) present and handled.
- Fiscal-year ranges exact and contiguous across 125 BS years — no gaps, no overlaps.

**BS is genuinely presentation-only**, which is the correct design and must be preserved:
`bs_accounting_dates.py:55-82` only sets XML `widget`/`options` attributes; nothing converts stored
values. The widget writes a luxon `DateTime` or `false` (`bs_date_field.js:89,96,191`), and
`onInputChange` converts through `bsToAd` **before** any write, so no BS string can reach the ORM.

## Component inventory

### Conversion — server (`custom_addons/l10n_np_bs/tools/bs.py`)

Pure functions; the only Odoo imports are `UserError` and `_` (`bs.py:19-20`). No model or registry
coupling, so it is freely movable.

| Function | Line | Returns | Errors |
|---|---|---|---|
| `to_np_digits(text)` | `:52` | `str` | never raises |
| `from_np_digits(text)` | `:57` | `str` | never raises |
| `ad_to_bs(value)` | `:66` | `(y,m,d)` or `None` | `UserError` out of range (`:75-80`); `None`→`None` |
| `bs_to_ad(y,m,d)` | `:84` | `datetime.date` | `UserError` on invalid BS date |
| `format_bs(value, fmt, np_digits=False, month_names=False)` | `:97` | `str` | `None`→`""` |
| `parse_bs(text)` | `:113` | `datetime.date` | `UserError`; accepts `-` and `/` only |
| `month_length(y,m)` | `:121` | `int` | **raw `KeyError`/`AssertionError`** — the one function that does not wrap |

Only **3 of the 7** have a production consumer. `format_bs`, `parse_bs`, `to_np_digits` and
`from_np_digits` are exercised only by tests.

### Conversion — browser (`static/src/bs_convert.js`)

Imports nothing but `./bs_calendar_data` (`:10-13`) — no `@web` imports at all. Exports
`BSRangeError`, `toNpDigits`, `fromNpDigits`, `bsMonthLength`, `adToBs`, `bsToAd`, `bsWeekday`,
`bsMonthName`, `bsWeekdayNames`, `formatBs`, `parseBs`, `BS_MIN_YEAR`, `BS_MAX_YEAR`.

All arithmetic is `Date.UTC`-based to avoid drift, documented at `:6-9`.

### Widget (`static/src/bs_date_field.js`)

Registered as `registry.category("fields").add("bs_date", bsDateField)` (`:226`).
`supportedTypes: ["date", "datetime"]` (`:205`); options `month_name`, `np_digits` (`:206-219`).
One service (`notification`, `:31`); no custom service is defined anywhere in the module.

### Arch injection (`custom_addons/l10n_np_accounting/models/bs_accounting_dates.py`)

`BsDateViewMixin` (`:33-37`) overrides `_get_view_cache_key` (`:44-52`) and `_get_view` (`:54-82`),
faithfully following core's own pattern in `res_currency.py:323-343` — including appending to the
cache key rather than rebuilding it.

Per-model coverage is a plain class attribute `_BS_DATE_FIELDS`:

| Model | Fields |
|---|---|
| `account.move` | `date`, `invoice_date`, `invoice_date_due`, `delivery_date` |
| `account.move.line` | `date`, `date_maturity` |
| `account.payment` / `.payment.register` | `date` / `payment_date` |
| `account.bank.statement` / `.line` | `date` |
| `account.lock.dates` | five lock dates |
| `account.financial.statements.wizard` | `date_from`, `date_to` |
| `l10n_np.vat.return`, `l10n_np.tds.certificate`, `l10n_np.tds.return` | `date_from`, `date_to` |
| `l10n_np.loan` / `.loan.line` | `date_start` / `date` |

**14 models, 20 field slots — 1.6% of the 237 business date fields.**

### The preference mechanism — group only

The answer matters, because the brief asks for a per-user preference and there isn't one:

1. `security/bs_date_group.xml:13-16` defines `group_bs_accounting_dates` — no category, no implications.
2. `res_config_settings.py:11-21` — `group_l10n_np_bs_accounting_dates` with
   `implied_group`. Odoo's convention adds the group to `base.group_user.implied_ids`, so ticking it
   enables BS for **every internal user**. Per-user opt-out requires a manual `group_ids` edit.
3. `res_company.py:13-18` — `l10n_np_bs_digits` (`latin` / `devanagari`), **style only, never a gate**.

**The only gate is `has_group(GROUP)`** (`bs_accounting_dates.py:61`).

The digit-style preference is **ignored in three places**: a hand-written
`<field widget="bs_date"/>` (defaults to Devanagari, `bs_date_field.js:222`), the Nepali Calendar
client action (hard-codes it, `bs_calendar_action.js:29`), and server-side entirely. Three sources
of truth for one user-visible setting.

## Defects that shape the design

Carried from the repository audit; each is confirmed.

| ID | Issue | Why it matters here |
|---|---|---|
| **BS-2** | `datetime` declared supported with **zero** zone normalisation — reads browser-local components; Odoo never sets `luxon.Settings.defaultZone` in production, so it follows the browser OS, not `res.users.tz` | Latent today (all covered fields are `date`). **94 of the 237 business fields are `datetime`** — going global exposes every one. This makes the timezone fix a prerequisite |
| **BS-1** | `tools/selftest.py` — the only exhaustive Python↔JS cross-check — is imported by nothing and `sys.exit`s from `main()` | The manifest's "can never drift apart" claim is enforced by a script nobody runs |
| **BS-3** | Search and group-by buckets stay Gregorian; a BS user filtering "August 2026" gets Bhadra 16 – Ashoj 15 | 22 business date fields appear in search views. This is where the localisation currently stops |
| **BS-4** | `month_length()` raises a raw `KeyError` at BS 2101, escaping the fiscal-year wizard's `UserError`-only catch — reachable **by default** from BS 2097 | Must be wrapped when the function moves |
| **BS-5** | The input is uncontrolled (`t-att-value` → `setAttribute`), so the DOM diverges from the record after typing | Core's own fields use `useInputField` for exactly this |
| **BS-6** | "Today" comes from `new Date()`, not `res.users.tz` | Widget and server disagree on today for part of each day |
| **BS-7** | `arch.iter('field')` walks nested subviews of **other** models while the guard checks only the outer model's `_fields` | Becomes materially riskier once coverage is global |
| **BS-8** | Only `form` and `list` are patched | 5 fields appear solely in kanban/pivot/graph/activity |

## Two "shared" APIs that disagree

Any central module must reconcile these rather than relocate them:

| Concern | Python | JavaScript |
|---|---|---|
| Digit default | `np_digits=False` (`bs.py:97`) | `npDigits: true` (`bs_convert.js:122`) |
| Accepted separators | `-` `/` (`bs.py:115`) | `-` `/` `.` whitespace (`bs_convert.js:135`) |
| Failure contract | raises `UserError` | returns `null` (`parseBs`) |
| Weekday names | long — `आइतबार` (`bs.py:40-41`) | short — `आइत` (`bs_calendar_data.js:158`) |
| Range constants | **absent**; hard-coded in an error string (`bs.py:78`) | `BS_MIN_YEAR`/`BS_MAX_YEAR` exported |
| Month-name format | `२०८३-भदौ-२४` (hyphens) | `२०८३ भदौ २४` (spaces) |

Month and weekday tables exist **three** times — `bs.py:31-41`, `bs_calendar_data.js:147-160`, and
hard-coded again in the generator `gen_js_data.py:96-109`. That third copy is the root cause of the
long/short weekday divergence, because the generator does not derive names from the library.

## Reports and exports — a green field

Stated as an absence, deliberately:

- **No** `format_date`/`format_datetime` override anywhere in `custom_addons`.
- **No** `ir.actions.report` record in any `l10n_np*` module.
- **No** QWeb report template in any `l10n_np*` module.
- **No** `ir.qweb` or `ir.qweb.field.date` extension.

Consequence: BS is screen-only. Every printed PDF, every xlsx export, and the TDS certificate and
VAT return outputs render Gregorian. `bs.format_bs` exists precisely for this and has no caller.

## Dependency analysis for extraction

**Safe to move down** (no upward references): `tools/bs.py`, `bs_calendar_data.js`,
`bs_convert.js`, `bs_date_field.*`, `bs_calendar_action.*`. `l10n_np_bs/__manifest__.py:35`
declares only `depends: ['web']`, which is what makes a lower core module viable.

**Three cycle-blockers** prevent moving `BsDateViewMixin` as written:

1. `GROUP = 'l10n_np_accounting.group_bs_accounting_dates'` (`:30`), read at `:51` and `:61`.
   → define the group in core; point the settings `implied_group` at the core id.
2. `self.env.company.l10n_np_bs_digits` (`:52`, `:67`), a field owned by `l10n_np_accounting`.
   → move the field to core; keep only the `related` settings mirror upstream.
3. The 13 `_inherit` bindings name `account.*` and `l10n_np.*` models.
   → only the abstract mixin is portable; bindings stay with the module owning each model.

**Import paths that would break on a move:** three sites use
`odoo.addons.l10n_np_bs.tools.bs` — `generate_np_fiscal_year.py:39,50` and
`test_calendar_ui.py:70`. A one-line re-export shim in `l10n_np_bs/tools/bs.py` avoids touching
`l10n_np_fiscal_year` at all.

## Scale — the numbers that set the architecture

Measured against the live database (134 installed modules):

| Measure | Count |
|---|---|
| Stored `date`/`datetime` fields | **1,223** |
| …`create_date` / `write_date` | **961** |
| …other technical (mail, bus, sms, device, cron, config) | ~26 |
| **Business date fields** | **237** |
| …`date` (timezone-free) | 143 |
| …**`datetime`** (need UTC → user tz → BS) | **94** |
| Business fields rendered in **any** view | 182 |
| …in **form or list** — today's mechanism's reach | **177 (97%)** |
| …in **search** views | 22 |
| …only in kanban / pivot / graph / activity | 5 |

**The conclusion that decides the architecture:** the existing `_get_view` mechanism already reaches
97% of the rendered surface. Inverting its allowlist to an *exclusion* list achieves global coverage
without patching Odoo's `formatDate`/`parseDate` pipeline — much smaller blast radius, much better
upgrade safety. See [`02_ARCHITECTURE.md`](02_ARCHITECTURE.md).
