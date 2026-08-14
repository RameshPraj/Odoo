# BS calendar backlog — source of truth

Every item that is **not** being built in this pass, plus the defects the design must fix on the way.
Deduplicated; [`JIRA_BACKLOG.md`](JIRA_BACKLOG.md) turns the P0/P1 rows into tickets.

Priority per the brief: **P0** financial/data corruption or security · **P1** broken date behaviour or
major workflow · **P2** important missing coverage · **P3** UX · **P4** cleanup.

## In this pass — status

Verified by `-u nepali_calendar_core --test-enable --test-tags /nepali_calendar_core`:
**116 tests, 0 failed, 0 errors**, and the whole custom suite at **132 / 0 / 0** (baseline was 121).

| ID | Item | Pri | Effort | State |
|---|---|---|---|---|
| BSC-1 | `nepali_calendar_core`: move conversion, widget, calendar action; shim in `l10n_np_bs` | P1 | M | **Done.** Moved with `git mv` so history follows; `l10n_np_bs` re-exports `tools.bs`, leaving `l10n_np_fiscal_year` untouched |
| BSC-2 | **Timezone fix — prerequisite.** `datetime` must resolve UTC → user tz → BS; "today" from `res.users.tz` | **P1** | M | **Done** both sides. Server asserted on the discriminating instant (`2026-09-08 18:30 UTC` → BS 2083-05-24 in Kathmandu, 2083-05-23 in UTC); widget code fixed but not yet asserted |
| BSC-3 | Reconcile the Python/JS contract | P2 | S | **Done.** Names collapsed into `tools/names.py`, which the generator now *emits*; `npDigits` defaulted to `false` on both sides; JS day padding added; both weekday lengths exposed everywhere |
| BSC-4 | Wrap `month_length()` so BS 2101 raises `UserError`, not `KeyError` | P2 | XS | **Done** |
| BSC-5 | `calendar_system` on user + company; precedence, `SELF_*_FIELDS`, `context_get`, `_get_invalidation_fields`, `session_info` | P1 | M | **Done,** with the invalidation and self-service rights asserted |
| BSC-6 | Registry override + the exclusion list | P1 | M | **Code written, untested.** `formatters` dropped (see below); the dispatcher has no test — the largest open gap |
| BSC-7 | Migrate the group → company default; retire the group; **needs a version bump** | P1 | S | Not started |
| BSC-8 | Delete the local mixin and 13 bindings from `l10n_np_accounting` | P2 | S | Not started |
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
| BSD-3 | JS unit-test suite | **P1** | M | **Done for `bs_convert`** — 19 tests, executed in headless Chrome by `tests/test_js_unit.py`. Declaring a bundle only *compiles* it; nothing ran it before |
| BSD-4 | Generator drift test — nothing asserts the checked-in table still matches the library | P2 | S | **Done** — `selftest.check()` parses the generated artefact, so a stale checked-in file fails |
| BSD-5 | Pin `nepali_datetime` in a project-owned requirements file; it is declared in `external_dependencies` but absent from `requirements.txt`, so a fresh env cannot install the suite | **P1** | XS | Not started |
| BSD-6 | `gen_js_data.py` hard-coded a third copy of the name tables — the root cause of the long/short weekday divergence | P3 | S | **Done** — one source (`tools/names.py`), asserted byte-equal across layers |
| BSD-7 | Fiscal-year wizard bound-checks BS year; it approaches the 2100 ceiling by default from BS 2097 | P2 | XS | Not started |
| BSD-8 | Guard the arch walk by field **type** if any `_get_view` path is retained | P3 | XS | Moot — no `_get_view` path is retained |
| BSD-9 | **The dispatcher component is untested.** Nothing asserts a BS user gets `BSDateField` on a business field and Odoo's own widget on `create_date`. It is the mechanism all coverage rests on | **P1** | M | Open |
| BSD-10 | `bs_date_field` behaviour untested: render, type-and-commit, picker click, rejected input, and the timezone cases *through the widget* | **P1** | M | Open |
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
