# BS calendar backlog — source of truth

Every item that is **not** being built in this pass, plus the defects the design must fix on the way.
Deduplicated; [`JIRA_BACKLOG.md`](JIRA_BACKLOG.md) turns the P0/P1 rows into tickets.

Priority per the brief: **P0** financial/data corruption or security · **P1** broken date behaviour or
major workflow · **P2** important missing coverage · **P3** UX · **P4** cleanup.

## In this pass — status

Verified by `-u nepali_calendar_core --test-enable --test-tags /nepali_calendar_core`:
**116 Python tests plus 38 JavaScript tests, 0 failed, 0 errors.** That module-scoped figure still
holds, including on a `TEMPLATE` copy of the live database with the legacy setting switched on and
the migration applied.

> **Corrected 2026-08-15.** This paragraph used to add that "the whole custom suite runs at
> **138 / 0 / 0**". That was never the whole suite — it covered four modules. Run across all 16
> custom modules the figure is **304 tests, 0 failed, 15 errors**, and the suite is **not green**:
> all 15 errors are `date_range`, which depends only on `web` and so self-tests before `account`
> loads, hitting a `res_partner` not-null constraint. That is **TST-8** in
> [`../project-review/BACKLOG.md`](../project-review/BACKLOG.md) — pre-existing and structural, not a
> regression. Quote the module-scoped number or the whole-suite number, but do not let one stand in
> for the other.

| ID | Item | Pri | Effort | State |
|---|---|---|---|---|
| BSC-1 | `nepali_calendar_core`: move conversion, widget, calendar action; shim in `l10n_np_bs` | P1 | M | **Done.** Moved with `git mv` so history follows; `l10n_np_bs` re-exports `tools.bs`, leaving `l10n_np_fiscal_year` untouched |
| BSC-2 | **Timezone fix — prerequisite.** `datetime` must resolve UTC → user tz → BS; "today" from `res.users.tz` | **P1** | M | **Done and asserted on both sides,** on the discriminating instant (`2026-09-08 18:30 UTC` → BS 2083-05-24 in Kathmandu, 2083-05-23 in UTC) — server-side via the QWeb converter, browser-side through the widget *and* through the dispatcher |
| BSC-3 | Reconcile the Python/JS contract | P2 | S | **Done.** Names collapsed into `tools/names.py`, which the generator now *emits*; `npDigits` defaulted to `false` on both sides; JS day padding added; both weekday lengths exposed everywhere |
| BSC-4 | Wrap `month_length()` so BS 2101 raises `UserError`, not `KeyError` | P2 | XS | **Done** |
| BSC-5 | `calendar_system` on user + company; precedence, `SELF_*_FIELDS`, `context_get`, `_get_invalidation_fields`, `session_info` | P1 | M | **Done,** with the invalidation and self-service rights asserted |
| BSC-6 | Registry override + the exclusion list | P1 | M | **Done and tested.** `formatters` dropped (see below). Testing the selection exposed that the dispatcher **did not work at all** — see BSD-15 |
| BSC-7 | Migrate the group → company default; retire the group; **needs a version bump** | P1 | S | **Done** as `19.0.1.1.0`. Verified on a `TEMPLATE` copy of the live database, which had the checkbox **on** — the only state that proves anything. Live `odoo19` deliberately not upgraded |
| BSC-8 | Delete the local mixin and 13 bindings from `l10n_np_accounting` | P2 | S | **Done.** ~150 lines of BS machinery removed; the module keeps only what is Nepal-accounting-specific |
| BSC-9 | `ir.qweb.field.date` / `.datetime` override + output-mode setting | P1 | M | **Done,** all three modes plus the per-field `calendar` escape hatch |
| BSC-10 | Wire `selftest.py` into the suite (`check() -> list[mismatch]`) | P1 | S | **Done.** 46,022 days in 0.9s, so it runs in full rather than sampled |
| BSC-11 | Test matrix per [`TEST_PLAN.md`](TEST_PLAN.md) | P1 | L | Partly — see the status table there |

### Scope change, recorded rather than quietly applied

**BSC-6 lost its `formatters` override.** It could not have worked: `DateTimeField` imports
`formatDate` **statically**, so the registry is never consulted for field rendering; and the one real
consumer (list aggregates, `list_renderer.js:767-770`) is passed no model or field name, so the
exclusion list could not be honoured there — `create_date` totals would have silently rendered BS.
Replaced by a dispatcher component on the `fields` registry, which has the metadata the decision
needs. Coverage is unchanged. Full reasoning in [`02_ARCHITECTURE.md`](02_ARCHITECTURE.md).

## Deferred — search, filters, group-by

The largest remaining gap; without it BS stops where periodic reporting starts.

| ID | Item | Pri | Effort |
|---|---|---|---|
| BSF-1 | Declarative BS-month `customOptions` filters on the ~20 highest-value search views. **Genuinely upgrade-proof** — a supported arch feature, no JS | **P1** | M |
| BSF-3 | Stored indexed `bs_year_month` on the reporting models, grouped as an ordinary field. **The recommended route to correct BS boundaries** | **P1** | L |
| BSF-2 | Patch `SearchModel.prototype._getDateFilterDomain` + `_enrichItem` for global BS filter buckets | P2 | L |
| BSF-4 | BS labels on Gregorian group buckets — **only alongside BSF-3.** Alone it is worse than nothing: a label that reads "Bhadra" over Bhadra 16 – Ashoj 15 looks correct and is not | P3 | M |
| BSF-5 | Resolve BS smart-date input to absolute ISO before domain construction | P3 | S |

## Deferred — reports and exports

| ID | Item | Pri | Effort |
|---|---|---|---|
| BSR-4 | Convert the TDS certificate and VAT return outputs to BS/both | **P1** | M |
| BSR-3 | `format_date_bs` in `MailRenderMixin` eval context as a **new** key — never shadow `format_date` | P2 | S |
| BSR-5 | Per-document defaults with the SME (invoice, statement, certificate) | P2 | S |
| BSR-6 | Optional BS **column** for xlsx exports — additive only | P3 | M |

## Deferred — views and apps

| ID | Item | Pri | Effort |
|---|---|---|---|
| BSV-1 | BS labels on the calendar view (toolbar, headers, day cells) — patchable | P2 | M |
| BSV-2 | Per-app verification sweep: mark each `MODULE_COVERAGE.md` row *Tested* with a test | P2 | L |
| BSV-3 | Kanban / pivot / graph / activity — the 5 fields rendered only there | P3 | S |
| BSV-4 | Portal/website dates — needs `web.assets_frontend`, which does **not** inherit backend | P3 | M |
| BSV-5 | POS cashier UI and receipts — separate frontend bundle | P3 | L |

## Defects to fix on the way

| ID | Item | Pri | Effort | State |
|---|---|---|---|---|
| BSD-1 | Adopt `useInputField` — the input is uncontrolled (`t-att-value` → `setAttribute`), so the DOM diverges from the record after typing | P2 | S | Open |
| BSD-2 | Weekend shading in the date picker — the calendar action flags Saturday, the picker flags nothing. Two grids in one module disagree | P3 | XS | Open |
| BSD-3 | JS unit-test suite | **P1** | M | **Done** — 38 tests in two suites, executed in headless Chrome by `tests/test_js_unit.py`. Declaring an `assets_unit_tests` bundle only *compiles* it; nothing ran it before |
| BSD-4 | Generator drift test — nothing asserts the checked-in table still matches the library | P2 | S | **Done** — `selftest.check()` parses the generated artefact, so a stale checked-in file fails |
| BSD-5 | Pin `nepali_datetime`; declared in `external_dependencies` but absent from `requirements.txt`, so a fresh env could not install the suite | **P1** | XS | **Done.** `nepali-datetime==1.0.8.5` appended in a marked project-additions block, so the upstream section stays byte-identical. `tests/test_requirements.py` (6 tests) fails if the pin goes missing, drifts from the installed version, is loosened to `>=`, or if the private `_days_in_month` we call disappears — verified by removing the line and watching it go red |
| BSD-6 | `gen_js_data.py` hard-coded a third copy of the name tables — the root cause of the long/short weekday divergence | P3 | S | **Done** — one source (`tools/names.py`), asserted byte-equal across layers |
| BSD-7 | Fiscal-year wizard bound-checks BS year; it approaches the 2100 ceiling by default from BS 2097 | P2 | XS | Not started |
| BSD-8 | Guard the arch walk by field **type** if any `_get_view` path is retained | P3 | XS | Moot — no `_get_view` path is retained |
| BSD-9 | The dispatcher's **selection** was untested — the exclusion predicate and BS rendering were each covered, their composition was not | **P1** | M | **Closed.** The override became an exported idempotent `installCalendarOverrides(calendar)`; Odoo restores registries per test, so the tests drive the real production path. It immediately found BSD-15 |
| BSD-10 | `bs_date_field` **interaction** untested: type-and-commit, picker click, rejected input. Render and the timezone matrix are now covered | P2 | S | Partly |
| BSD-12 | `extractProps` defaulted `npDigits` to `true` while every other layer had moved to Latin, so `widget="bs_date"` rendered Devanagari and the dispatcher rendered ASCII | P2 | XS | **Fixed** — now falls back to the company setting |
| BSD-13 | Nothing parse-checked the JavaScript. A Python-style implicit string concatenation in a `_t()` call blanked the whole web client, reported only as a line number in a minified bundle | P2 | XS | **Fixed** — `TestBSAssets.test_all_js_parses_as_a_module` runs `node --input-type=module --check` over every `.js` file. Note `node --check <path>` does **not** catch it; the file must be piped as a module |
| BSD-14 | `calendar_service.js` was written to centralise "is BS active" but nothing could use it: registry overrides run at module import, before any service starts | P4 | XS | **Removed** rather than left as a decorative abstraction |
| BSD-11 | `res_company.calendar_system` is `required=True`, so the resolver's `or 'ad'` third level is unreachable from the database. Kept as defence in depth and tested on in-memory records; if `required` is ever dropped, the SQL-level test must come back | P4 | XS | Documented |

## Explicitly not planned

| Item | Why |
|---|---|
| BS-bounded calendar month view | Needs a custom FullCalendar view plugin. Use the standalone client action instead |
| Wrapping `luxon.DateTime.prototype.toFormat` / `toLocaleString` | The only universal chokepoint, but it rewrites dates in contexts we do not control (debug menus, tooltips, column-width measurement, domain editor) and risks corrupting round-trips |
| Monkeypatching `tools.misc.format_date` | 218 unfunnelled call sites, ~15 of which build **legal e-invoicing payloads** that must stay Gregorian |
| Modelling BS as a `res.lang` variant | `date_format` is a 9-value Gregorian `Selection`; lang also selects the `.po` and asset bundle, so `English + BS` would become impossible |
| Storing BS values in the database | Violates the canonical-storage principle; nothing needs it |
| Overriding `convert_to_export` / `convert_to_display_name` | `convert_to_export` calls `convert_to_display_name`, so this silently corrupts every export and breaks re-import |

## Discovered while building, not planned for

| ID | Item | Pri | Effort | State |
|---|---|---|---|---|
| BSD-15 | **The dispatcher did not work at all.** Owl validates props strictly and the wrapper forwarded its own synthetic props to components declaring neither, so with `calendar_system='bs'` every date field raised `Invalid props` and failed to render. The primary path was dead and nothing caught it, because the only untested seam was the one choosing the widget | **P0** | S | **Fixed** — per-branch prop filtering, plus the selection tests that would have caught it |
| BSD-16 | The plan's Phase 4b said to move the group into core and re-point `implied_group`. There is no group in core — the preference replaced it. Two mechanisms gating one behaviour would let a user satisfy one and not the other | P3 | XS | **Resolved** by deleting the group outright |
| BSD-17 | The plan's migration was to detect users individually removed from the group and pin them to AD. That state cannot exist: `has_group` is True for a group implied by `base.group_user` regardless of direct membership, so the old mechanism never supported an individual opt-out | P4 | XS | **Dropped** — code for it would have looked thorough and done nothing |
| BSD-18 | Migration tests depended on whether the host database had already been upgraded, so "must stay Gregorian" failed on a migrated one for reasons unrelated to the migration | P3 | XS | **Fixed** — the fixture defines its own "before" |

## Top risks

1. **The 94 `datetime` fields.** Today zero reach the widget, so the missing timezone handling is
   latent. The global override exposes all 94 at once — hence BSC-2 before BSC-6, not after.
2. **View-cache leakage** if any `_get_view` route is retained: the default cache key has **no uid**,
   so one user's calendar can be served to another. The registry route avoids this; a test must keep
   it avoided.
3. **`convert_to_export` → `convert_to_display_name`** — the quiet export-corruption path.
4. **No upstream contract.** First alternate-calendar layer in this codebase; every seam needs a
   per-major smoke test.
5. **Migration tested in the wrong state** — verifying it on a database where the group was never set
   proves nothing.
