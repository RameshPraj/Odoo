# Jira backlog — BS calendar

Tickets for every **P0/P1** in [`BACKLOG.md`](BACKLOG.md), plus the P2s that share an epic.
Effort XS <½d · S ½–1d · M 2–3d · L 1–2w · XL >2w.

> **Status is tracked in [`BACKLOG.md`](BACKLOG.md#in-this-pass--status), not here.** These tickets are
> the original written-up work items and are kept as written, so that what was planned can be compared
> against what was built. Several are now done, two were dropped as based on a misreading, and one new
> **P0** was found that no ticket anticipated:
>
> | | |
> |---|---|
> | Done | BS-101, BS-102, BS-103, BS-104, BS-105, BS-106, BS-107, BS-108, BS-110 |
> | Dropped | the `formatters` registry override (could not work); per-user opt-out detection in the migration (the state cannot exist) |
> | **New P0** | the dispatcher raised `Invalid props` and **no date field rendered** for a BS user — the primary path was dead. Found only when the selection was finally tested. Fixed; see BSD-15 |
>
> Acceptance criteria referring to "121 tests green" now read **138**.

---

## EPIC-BS-1 · Central framework

### BS-101 — Extract `nepali_calendar_core`
**Task · P1 · M**
**Problem** Conversion, widget and calendar action live in `l10n_np_bs`; the arch mixin lives in
`l10n_np_accounting` and reaches upward three times, so nothing is reusable outside Accounting.
**Solution** New module `depends: ['web']`. Move `tools/bs.py`, `bs_calendar_data.js`,
`bs_convert.js`, `bs_date_field.*`, `bs_calendar_action.*`. Leave a re-export shim in
`l10n_np_bs/tools/bs.py` so `l10n_np_fiscal_year` is untouched.
**Acceptance** All 15 modules install from a clean venv · `l10n_np_fiscal_year` unmodified ·
existing 121 tests green.
**Risks** Three cycle-blockers must be resolved first: the hard-coded group xml-id, the company digit
field, and the model bindings. **Dependencies** BS-104 (version bumps).

### BS-102 — Fix datetime timezone handling
**Bug · P1 · M · PREREQUISITE**
**Problem** The widget declares `supportedTypes: ["date","datetime"]` but applies **zero** zone
normalisation. It reads browser-local components, and Odoo never sets `luxon.Settings.defaultZone` in
production — so it follows the browser OS, not `res.users.tz`.
**Evidence** `2026-09-08 19:00 UTC` renders BS 2083-05-24 in Kathmandu, 2083-05-23 in UTC — a
day-boundary error for 5h45m daily.
**Impact** Latent today (all covered fields are `date`). **94 of 237 business fields are `datetime`**,
so BS-106 exposes every one.
**Solution** UTC → user tz → local AD Y/M/D → BS. "Today" from `res.users.tz`, not `new Date()`.
**Acceptance** The timezone matrix in `TEST_PLAN.md` §2 passes for Kathmandu, UTC, New York, Kolkata.
**This must land before BS-106.** Getting the order wrong ships 94 silently wrong fields.

### BS-103 — Reconcile the Python/JS contract
**Task · P2 · S**
Digits default to Latin on both · accept `-` `/` `.` whitespace on both · keep raise-vs-null but
document it · expose short **and** long weekday names · export `BS_MIN_YEAR`/`BS_MAX_YEAR` from Python
and interpolate them into the error message · month names from a single source (the generator).
**Acceptance** A parity test asserts identical output for identical input.

### BS-104 — Version bumps and migration scaffolding
**Task · P1 · S**
**Problem** All modules frozen at `19.0.1.0.0` with no `migrations/`, so Odoo never runs an upgrade —
which means BS-107's migration cannot execute at all.
**Blocks** BS-101, BS-107.

### BS-105 — Wrap `month_length()`
**Bug · P2 · XS**
Raises a raw `KeyError` at BS 2101 and `AssertionError` for month 13, escaping the fiscal-year
wizard's `UserError`-only catch. **Reachable by default from BS 2097** (the wizard defaults to
`current + 4`). Also bound-check the wizard (BSD-7).

---

## EPIC-BS-2 · Preference and coverage

### BS-106 — Calendar preference + global coverage
**Story · P1 · M**
**Problem** BS is gated by a security group granted to `base.group_user` — database-wide, no per-user
choice — and covers 20 of 237 fields.
**Solution** `res.users.calendar_system` + `res.company.calendar_system`, precedence user → company →
AD. Coverage via `registry.category("fields"|"formatters"|"parsers").add(…, { force: true })` plus one
exclusion list.
**Acceptance** Precedence table in `TEST_PLAN.md` §3 passes · a non-admin sets their own preference ·
a preference change takes effect on the **next request** · ~177 form/list fields render BS ·
`create_date` still renders AD.
**Risks** Two silent failures: omitting `calendar_system` from `_get_invalidation_fields`
(`res_users.py:735-740`) leaves `context_get`'s `ormcache('self.env.uid')` stale until restart; and
putting it in `lang_params` would cross-contaminate users, because
`_get_web_translations_hash` is `ormcache('frozenset(modules)','lang')` with **no uid** and is served
`Cache-Control: public`.
**Dependencies** BS-102 must be complete.

### BS-107 — Migrate the group to a company default
**Task · P1 · S**
If the group is granted to `base.group_user`, set `company.calendar_system = 'bs'` so **everyone keeps
seeing BS**; users explicitly removed from the group get `calendar_system = 'ad'`; then retire the
group.
**Acceptance** Verified on a database that **actually has the group set** — a migration tested only
where the feature was off proves nothing.
**Dependencies** BS-104, BS-106.

### BS-108 — Remove the local mixin from `l10n_np_accounting`
**Task · P2 · S**
Delete `BsDateViewMixin` and the 13 bindings (~150 lines). **Land after** BS-106 is proven, not in the
same change — so a regression is attributable.
**Acceptance** The 16 existing BS-date tests pass, re-pointed at core.

---

## EPIC-BS-3 · Reports

### BS-109 — QWeb BS formatter
**Story · P1 · M**
**Problem** No BS in any report. `format_bs` exists with **zero callers**; every PDF, xlsx and the TDS
certificate and VAT return render Gregorian.
**Solution** Override `value_to_html` on **both** `ir.qweb.field.date` and `ir.qweb.field.datetime` —
they do not share an implementation (`.date` delegates to `tools.format_date`, `.datetime` calls Babel
directly). Add a company output mode: `ad` / `bs` / `both`.
**Acceptance** Both converters tested separately · all three modes render · **a CSV/XLSX export by a
BS user is byte-identical to an AD user's**.
**Risks** Do **not** override `convert_to_export` or `convert_to_display_name` — the former calls the
latter, so this silently corrupts every export and breaks re-import. Do **not** monkeypatch
`tools.format_date`: 218 call sites, ~15 building legal e-invoicing payloads that must stay Gregorian.

### BS-110 — TDS certificate and VAT return outputs in BS
**Task · P1 · M** — the statutory documents a Nepali user actually files.
**Dependencies** BS-109. **Also needs** SME sign-off on per-document format.

---

## EPIC-BS-4 · Verification

### BS-111 — Wire `selftest.py` into the suite
**Task · P1 · S**
**Problem** The only exhaustive Python↔JS cross-check — all 46,022 days — is imported by nothing and
`sys.exit`s from `main()`. The manifest's "can never drift apart" claim is enforced by a script nobody
runs.
**Solution** Split into `check() -> list[mismatch]`; keep printing/exit in the `__main__` shim.
**Acceptance** The sweep runs in CI and fails on any divergence.
**Highest value per unit effort in this project** — the verification already exists and already works.

### BS-112 — JavaScript unit-test suite
**Task · P1 · M**
`static/tests/` is declared in the manifest and is **empty and untracked**, so it does not exist on a
fresh clone. Every conversion, boundary and timezone concern lives in untested JS.
**Acceptance** `bs_convert` vectors matching the Python tests · widget render/type/pick · the
timezone cases from BS-102 · registry override on/off · exclusions honoured.

### BS-113 — ORM invariance test
**Task · P1 · S**
Create the same records as a BS user and an AD user; assert the raw PostgreSQL columns are
**identical**, read with raw SQL so no ORM conversion can hide a difference.
**Acceptance** Holds for `account.move` (date), `stock.picking` (datetime) and `l10n_np.loan`.
This is the test that proves the canonical-storage principle.

### BS-114 — Pin `nepali_datetime`
**Task · P1 · XS**
Declared in `external_dependencies`, **absent from `requirements.txt`**, unpinned, and we call the
private `_days_in_month`. A fresh environment cannot install the suite at all.

### BS-115 — Security and SaaS isolation tests
**Task · P2 · S**
A BS user sees exactly the records an AD user sees · the preference is read without `sudo()` · two
users with different preferences are never served each other's rendering · two databases with opposite
company defaults do not bleed.

---

## EPIC-BS-5 · Search and group-by (deferred)

### BS-116 — Declarative BS-month filters on high-value search views
**Story · P1 · M**
**Problem** A BS user filtering "August 2026" gets BS Bhadra 16 – Ashoj 15. Every BS period splits.
**Solution** `<filter>` with `granularity: "withDomain"` and `customOptions` — a supported arch
feature, **zero JS, genuinely upgrade-proof**. Apply to the ~20 views that matter.
**Acceptance** Selecting a BS month returns **only** records in that BS month. This single assertion
is the acceptance test for BS localisation as a whole.

### BS-117 — Stored `bs_year_month` for correct group boundaries
**Story · P1 · L**
The granularity registry is **not viable**: PostgreSQL has no `date_trunc('bs_month', …)` and a BS
month is not a `relativedelta`. An indexed stored column grouped as an ordinary field gives correct
boundaries with no core patch.
**Acceptance** Group boundaries align with BS months, not merely the labels.
**Note** BSF-4 (BS labels on Gregorian buckets) must **not** ship without this — a label reading
"Bhadra" over Bhadra 16 – Ashoj 15 looks correct and is not.

---

## Summary

| Epic | Tickets | P1 |
|---|---:|---:|
| 1 Central framework | 5 | 3 |
| 2 Preference and coverage | 3 | 2 |
| 3 Reports | 2 | 2 |
| 4 Verification | 5 | 4 |
| 5 Search and group-by (deferred) | 2 | 2 |
| **Total** | **17** | **13** |

**Ordering that matters:** BS-104 → BS-101 → **BS-102** → BS-106 → BS-107 → BS-108. BS-102 before
BS-106 is not a preference; skipping it ships 94 silently wrong datetime fields.
