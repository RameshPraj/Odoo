# 02 — Architecture

Design for BS as a platform capability. Every seam below was verified against Odoo 19 source and
is labelled **SAFE SEAM** (registry/service/documented override), **PATCH** (justified, needs a
per-major smoke test), or **NOT VIABLE**.

> **Design change from the initial plan, recorded deliberately.** The plan proposed inverting the
> `_get_view` allowlist as the primary mechanism. Seam analysis found a better one — the JS
> **field/formatter/parser registries**. It needs no field enumeration, covers form, list and
> kanban in one place, and avoids the single highest-risk trap in this area: `_get_view_cache`
> returns a **group-unfiltered arch whose default cache key contains no uid**
> (`ir_ui_view.py:3082-3084`), so any arch mutation keyed on a user preference leaks across users
> unless the key is extended. The registry route sidesteps that entirely.

## Principle 1 — canonical storage is untouchable

PostgreSQL keeps AD `date` / `timestamp`. The ORM, domains, RPC, exports and imports continue to
see standard Odoo values. BS exists only in **display** and **input**.

The ORM makes this structurally easy: there is **no display-formatting hook on `fields.Date` /
`fields.Datetime` at all**. The web client receives raw ISO and formats in luxon. So a BS layer is
*forced* to be presentation-only.

**Three functions must never be overridden.** This is the most dangerous coupling in the design:

| Do not touch | Why |
|---|---|
| `Date.to_string` / `to_date`, `Datetime.to_string` / `to_datetime` (`fields_temporal.py:137-265`) | Define the server wire format. Every RPC payload, domain literal and SQL parameter uses them |
| `Date.convert_to_export`, `Datetime.convert_to_export` (`:184-185`, `:287-289`) | Export must stay Gregorian ISO for round-trip fidelity |
| `Datetime.convert_to_display_name` (`:291-294`) | **`convert_to_export` calls it.** "Just overriding display name" silently corrupts every CSV/XLSX export and breaks re-import |

## Principle 2 — the calendar is orthogonal to language

`calendar_system` is a per-user presentation axis, a **sibling of `tz`**, not a variant of `lang`.

**Modelling it on `res.lang` is NOT VIABLE**, confirmed:
- `date_format` is a `Selection` of **9 hard-coded Gregorian patterns** (`res_lang.py:58-70`) with a
  validator (`:129-137`). No strftime/LDML directive means "Bikram Sambat year".
- Babel has **no calendar-system parameter** — every `babel.dates.format_*` in Odoo is Gregorian.
- `lang` also selects the `.po` bundle and the JS asset bundle, so BS-via-lang would force a
  translation set. The brief explicitly requires `English + BS` and `Nepali + AD` to both work.
- `base_import.py:700` sniffs incoming CSV dates using `res.lang.date_format` **first** — changing
  it would make the importer try to parse Gregorian files with a BS pattern.

This also confirms Odoo has **no** alternate-calendar support anywhere: an exhaustive grep for
`hijri|jalali|buddhist|bikram|calendar_system` across core returns two false positives (an ACL id
and an emoji name). Luxon 3.5 *can* proxy to Intl's `ca-` extension, but Intl has **no Bikram
Sambat value** — so that tempting built-in hook cannot deliver BS. We are building the first such
layer in this codebase; no upstream contract will be maintained for us.

## Preference resolution

`user.calendar_system` → `company.calendar_system` → `'ad'`. One helper, called once; never
duplicated as `if user.bs_enabled` across models.

**Server plumbing — all SAFE SEAM:**

| Step | Seam | Note |
|---|---|---|
| Field on `res.users` | ordinary field | |
| User may set their own | override `SELF_READABLE_FIELDS` / `SELF_WRITEABLE_FIELDS` (`res_users.py:175-193`) | Docstrings explicitly invite the override |
| Reaches `env.context` server-wide | override `context_get()` (`res_users.py:694-723`) | Only `lang` and `tz` are read today; adding a key lands it in `env.context` for free |
| **Cache invalidation** | add `calendar_system` to `_get_invalidation_fields()` (`res_users.py:735-740`) | **Non-negotiable.** `context_get` is `ormcache('self.env.uid')`; without this it stays stale until restart |
| Reaches the browser | override `session_info()` (`web/models/ir_http.py:79`) | ~20 core addons already override it. `user_context` is already shipped at `:103` |
| Preferences UI | xpath into `<group name="other_calendar_preferences"/>` (`res_users_views.xml:459`) | An anchor placed there for exactly this |

**Trap avoided:** the preference must **not** ride on `lang_params` /
`_get_translations_for_webclient`. That payload is `ormcache('frozenset(modules)', 'lang')` — **no
uid** (`base/models/ir_http.py:436`) — and is served `Cache-Control: public` (`webclient.py:84-86`).
Putting a per-user value there cross-contaminates users *and* browser/CDN caches.

## Display layer — the primary mechanism

**Two registry overrides, both SAFE SEAM.** Odoo 19 has **one** component behind `date`,
`datetime` and `daterange` (`datetime_field.js:45`, registered `:587-591`), and the registry
supports deliberate replacement via `add(key, value, { force: true })` (`core/registry.js:99`).

| Registry | Covers | Reference |
|---|---|---|
| `fields` — `date`, `datetime`, `daterange` | form fields, kanban (renders `Field`), list cells | `datetime_field.js:587-591` |
| `parsers` — `date`, `datetime` | search-bar typing and field input | `views/fields/parsers.js:218-219` |

> **Correction, made during implementation.** This section previously listed a **third** override,
> on the `formatters` registry. That would not have worked, and the design was changed rather than
> shipped:
>
> 1. `DateTimeField.getFormattedValue` imports `formatDate` **statically** from `../formatters`. A
>    registry entry is therefore never consulted for field rendering — the override would have had
>    no effect on the thing it was added for.
> 2. The registry *is* used for list **aggregates**, but that call site
>    (`list_renderer.js:767-770`) passes only `digits` / `escape` / `currencyId` — no model or field
>    name. The exclusion list could not have been honoured there, so `create_date` totals would have
>    silently rendered BS.
>
> Coverage is unaffected: the `fields` override reaches the same surface, and it does so with the
> field metadata the exclusion check needs.

The `fields` entry is a small **dispatcher** component. It cannot decide BS-or-native at
registration time, because the decision depends on the record's model and the field's name, neither
of which exists until render. So it renders `BSDateField` or delegates to the native component it
displaced, per field, at render time. The native `extractProps` is preserved and re-invoked, so
options already written into existing views keep working.

The preference arrives via **`session_info`** (`web/models/ir_http.py:79`) — the same channel `tz`
and `uid` use, with roughly twenty core precedents. Read once at module load: changing the
preference triggers Odoo's own `reload_context` client action, so there is no live-switch case.

> **Not** via `_get_web_translations_hash`: it is `ormcache('frozenset(modules)', 'lang')` with **no
> uid** *and* served `Cache-Control: public`. A per-user value placed there would be handed to
> whoever asked next — a cross-user leak, and in a multi-tenant deployment a cross-tenant one.

The component branches on that preference and on an **exclusion set** keyed by
`(resModel, fieldName)` — both available in `standardFieldProps`. So:

- **No field enumeration.** The 1,223-field problem disappears; only exclusions are listed.
- **No `_get_view` involvement**, therefore no view-cache leakage risk.
- Odoo's own `bs_date` widget already proves the pattern (`bs_date_field.js:226`); it simply is not
  registered against the native names.

**Exclusions** live in one place in core: `create_date` / `write_date` (961 of the 1,223 fields),
plus technical models (`mail.*`, `bus.*`, `sms.*`, `res.device*`, `ir.cron*`, `ir.config*`) and a
named per-field opt-out. Measured effect: **237 business date fields remain**, of which 182 render
in a view.

**Gotcha designed around:** the default field render path is `toLocaleDateString` → **Intl**
(`formatters.js:90` → `dates.js:445`), *not* `localization.dateFormat`. Overriding `dateFormat`
looks like it does nothing. And `localization` is a **throwing Proxy**
(`core/l10n/localization.js:26-40`) — reading an unset key raises rather than returning `undefined`.

**Rejected:** wrapping `luxon.DateTime.prototype.toFormat` / `toLocaleString`. It is the only truly
universal chokepoint and would catch all 141 importers of `@web/core/l10n/dates` at once — but it
also rewrites dates in contexts we do not control (debug menus, tooltips, column-width measurement,
domain tree editor) and risks corrupting round-trips. Too blunt.

## Timezone — a prerequisite, not a follow-up

`date` fields are timezone-free and safe. **`datetime` is not**, and 94 of the 237 business fields
are `datetime`.

The correct chain is **UTC → user tz → local AD Y/M/D → BS**, never UTC → BS.

Today the widget reads **browser-local** components with zero normalisation, and Odoo never assigns
`luxon.Settings.defaultZone` in production, so "default" is the browser OS zone — not
`res.users.tz`. A datetime at `2026-09-08 19:00 UTC` renders BS 2083-05-24 in Kathmandu and
2083-05-23 in UTC.

This is latent only because every currently-covered field is a `date`. **Going global exposes all
94 at once**, so the fix lands *before* the registry override. Server-side the precedent is exact:
`Datetime.context_timestamp` (`fields_temporal.py:210-229`) reads `record.env.tz`. "Today" must come
from the same place, not `new Date()`.

## Reports and exports

**SAFE SEAM, and a green field** — there is no BS report formatting today at all.

Override `ir.qweb.field.date.value_to_html` and `ir.qweb.field.datetime.value_to_html`. This is an
officially documented extension point (`ir_qweb.py:686-687`: *"to customize `t-field` rendering,
subclass `ir.qweb.field`"*), dispatched dynamically at `:2761-2762`, with core precedent in
`html_editor/models/ir_qweb_fields.py`.

Two asymmetries to handle rather than trip over:
- `ir.qweb.field.date` delegates to `tools.format_date` (`ir_qweb_fields.py:274`), but
  `ir.qweb.field.datetime` calls **Babel directly** (`:328-332`). Both need overriding.
- Plain `ir.actions.report` QWeb has **no `format_date` in its render context** at all
  (`ir_qweb.py:1294-1329`, `ir_actions_report.py:1125-1142`). Only `MailRenderMixin` injects it
  (`mail_render_mixin.py:311-333`).

**Not doing:** monkeypatching `tools.misc.format_date`. There are **218 call sites** across ~130
files, none funnelled, and several build **legal e-invoicing payloads**
(`account_edi_ubl_cii`, `l10n_es_edi_tbai`) that must stay Gregorian. Instead: the `ir.qweb.field.*`
override plus an explicit `format_date_bs(env, value)` helper for the human-facing sites we choose.

**Export stays Gregorian**, per Principle 1. If BS export is ever wanted, add a separate computed
Char column — additive, cannot break round-trips.

**Configurable output** per the brief: `2083-04-29 BS` or `2083-04-29 BS (2026-08-14 AD)`, resolved
by the central formatter from a company setting — never hard-coded per report.

## Search, filters and group-by — deferred, with the design settled

Not in this pass; documented so the backlog is executable rather than aspirational.

**Filters — PATCH, or better, declarative.** Buckets are computed in
`search/utils/dates.js:140-172` `constructDateRange`, using luxon `startOf`/`endOf` — Gregorian.
`SearchModel.prototype._getDateFilterDomain` (`search_model.js:1567`) and `_enrichItem` (`:1353`)
are the two prototype methods that own bucket→domain and the option list; patching them is the
global fix. **But the genuinely upgrade-proof answer is declarative**: `<filter>` with
`granularity: "withDomain"` and `customOptions` (`utils/dates.js:265-274`,
`search_arch_parser.js:308`) injects arbitrary BS-month filters per search view with **zero JS**.
Preferred for the 22 fields that actually appear in search views.

**Group-by — the granularity registry is NOT VIABLE.** `READ_GROUP_TIME_GRANULARITY`
(`orm/utils.py:22-29`) values must be `relativedelta`s, and the granularity name is interpolated
into `date_trunc(%s, …)` (`orm/models.py:2109`). BS months are 29–32 days from a per-year lookup
table — not a `relativedelta` — and there is no `date_trunc('bs_month', …)`.

Two viable routes, in order of preference:
1. **Relabel Gregorian buckets in BS** — SAFE SEAM. Override `_web_read_group_groupby_formatter`
   (`web/models/models.py:1168`). Six core precedents. `__range` stays ISO so drill-down keeps
   working. Honest but imperfect: the *boundaries* remain Gregorian.
2. **A stored computed `bs_year_month` column**, indexed, grouped as an ordinary field — correct
   boundaries, no core patch, no granularity registry. **This is the recommended design** for true
   BS-period reporting.

Group labels are **server-produced** (`model/relational_model/utils.js:627-631`;
`pivot_model.js:928`), so this cannot be solved in JS at all.

## Calendar view — labels only

**PATCH for labels; FORK for BS-bounded grids — so we will not do the latter.**

FullCalendar computes its own Gregorian month range; a true BS-month grid needs a custom view
plugin. Toolbar titles (`calendar_controller.js:120-165`) and column headers
(`calendar_common_renderer.js:405-423`) are patchable prototype members, and day-cell numbers are
reachable by adding a `dayCellContent` callback to `get options`.

For a genuinely BS-bounded calendar, keep the **standalone client action** already in
`bs_calendar_action.js`. That pattern is right; keep it.

## Module layout

```
nepali_calendar_core            depends: ['web']
├── tools/bs.py                 AD↔BS, format, parse, month_length  (moved)
├── tools/selftest.py           check() -> list[mismatch]           (refactored, wired to tests)
├── models/res_users.py         calendar_system + SELF_*_FIELDS + context_get + _get_invalidation_fields
├── models/res_company.py       calendar_system default + digit style
├── models/ir_http.py           session_info
├── models/ir_qweb_fields.py    BS report formatting
├── static/src/bs_calendar_data.js   (generated, moved)
├── static/src/bs_convert.js         (moved)
├── static/src/calendar_service.js   resolves the preference client-side
├── static/src/bs_date_field.js      (moved + timezone fix)
├── static/src/registry_overrides.js fields / formatters / parsers, force: true
└── static/src/exclusions.js         the one exclusion list

l10n_np_bs                      thin shim: re-exports tools.bs so
                                l10n_np_fiscal_year needs no change
l10n_np_accounting              keeps its model bindings only; drops its own mixin
```

**Three cycle-blockers resolved by this layout:** the group and the digit field move to core, and
only the abstract mechanism moves — model bindings stay with the module owning each model.

## SaaS isolation

Satisfied without extra machinery: the preference is a per-database `res.users` / `res.company`
field, and every cache key is per-user or per-company. Specifically —
`ormcache('self.env.uid')` on `context_get` is already per-user; the lang-keyed, HTTP-public
translations cache is **avoided by design** (see the trap above), which is the only place a
cross-tenant leak was possible.

## Performance

- Conversion is table-driven and deterministic; memoise per `(y, m)` where useful.
- The registry route adds **no server work at all** — no arch walking, no extra view-cache entries.
  This is a further advantage over the `_get_view` approach.
- Prefer a low-cardinality discriminator (`'bs'` / `False`) over `uid` in any cache key, to keep
  hit rates high — the precedent is `project_task.py:1003`, which keys on a boolean rather than uid.

## Security

Calendar preference is display-only and grants no data access. It must never be read with `sudo()`;
`SELF_READABLE_FIELDS` is exactly the mechanism that makes a plain read work. Domains continue to
be built from ISO strings — BS never reaches a domain, so no injection surface is added.
