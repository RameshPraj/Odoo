# Search and filters

**Status: deferred to backlog. Design settled, so the work is executable rather than aspirational.**

This is the item the brief calls critical, and it is where the localisation currently stops: dates
display in BS right up until you report by period — which is most of what an accountant does.

## The problem, precisely

A BS user selecting **"August 2026"** gets the domain `2026-08-01 … 2026-08-31`, which is
**BS Bhadra 16 – Ashoj 15** — straddling two BS months. Every BS period is split.

Bucket boundaries are computed in `search/utils/dates.js:140-172` `constructDateRange`:

```js
const leftDate  = date.startOf(granularity);   // luxon → Gregorian
const rightDate = date.endOf(granularity);     // luxon → Gregorian
leftBound  = fieldType === "date" ? serializeDate(leftDate) : serializeDateTime(leftDate);
const domain = new Domain(["&", [fieldName, ">=", leftBound], [fieldName, "<=", rightBound]]);
```

Quarters are hard-coded Gregorian (`utils/dates.js:8-13`). 22 business date fields appear in search
views.

**The invariant that must hold** — and the reason this is tractable at all:

```
BS input  →  AD domain/query  →  correct records  →  BS display
```

The database is never queried against a BS string. Only the *boundary computation* changes.

## Filters — two routes

### Route A (preferred): declarative, per search view

Odoo has a real arch-level extension point: `<filter>` with `granularity: "withDomain"` and
`customOptions` (`utils/dates.js:265-274`, honoured at `:84-89`, parsed at
`search_arch_parser.js:308`). This injects arbitrary BS-month filters **with zero JavaScript**.

- **Genuinely upgrade-proof** — it is a supported arch feature, not a patch.
- Practical for the ~20 high-value search views (invoices, journal items, sales, purchases, stock).
- Impractical to blanket across all of Odoo.

**Recommended for the fields that matter.**

### Route B: patch two prototype methods

For global coverage, patch exactly two methods on an exported class:

| Method | Owns |
|---|---|
| `SearchModel.prototype._getDateFilterDomain` (`search_model.js:1567`) | bucket → domain, **and** the facet description |
| `SearchModel.prototype._enrichItem` (`search_model.js:1353`, `dateFilter` branch `:1370`) | the option list in the dropdown |

Both are stable across 17→19. `search/utils/dates.js` itself is **not** patchable — its functions
are plain module exports statically imported into `search_model.js:15-20`.

Replacing `SearchModel` per view is possible (`views/view.js:432`) but is per-view-type, so it is
worse than one prototype patch.

## Group-by — the granularity registry is NOT VIABLE

This must be stated plainly because it looks like the obvious approach and is a dead end.

`READ_GROUP_TIME_GRANULARITY` (`orm/utils.py:22-29`) maps a granularity name to a
`dateutil.relativedelta`, and the name is interpolated straight into SQL:

```python
sql_expr = SQL("date_trunc(%s, %s::timestamp)", granularity, sql_expr)   # orm/models.py:2109
```

Two hard blockers:

1. **PostgreSQL has no `date_trunc('bs_month', …)`.** The accepted values are
   `microseconds … millennium`.
2. **A BS month is not a `relativedelta`.** BS months are 29–32 days from a per-year lookup table,
   and the value is used for arithmetic in three places (`models.py:2591`,
   `web/models/models.py:1099,1214`).

Additionally both label formatters index `READ_GROUP_DISPLAY_FORMAT[granularity]` and would
`KeyError` on a new key, and `fields_temporal.py:74-92` raises hard `ValueError`s on unknown
property names.

**Group labels are also server-produced**, so none of this is solvable in JS:
`model/relational_model/utils.js:627-631` returns `rawValue[1]` — the label the server already
formatted. Pivot goes the same way (`pivot_model.js:928`).

### Two viable routes, in order of preference

**Route 1 — a stored computed column. Recommended.**

Add an indexed `bs_year_month` (Char or Integer) to the models that need BS period reporting, and
group by it as an ordinary field.

- **Correct boundaries** — Shrawan 1 really is the start of the group.
- **No core patch, no granularity registry, no SQL surgery.**
- Sorts correctly if encoded `YYYYMM` as an integer.
- Cost: a stored field per model, kept current by a compute — the only real downside, and it is the
  same trade Odoo itself makes for other denormalised reporting fields.

**Route 2 — relabel Gregorian buckets in BS.** SAFE SEAM, but honest about what it is: override
`_web_read_group_groupby_formatter` (`web/models/models.py:1168`) so the group header reads
`"2083 Bhadra"`. Six core precedents exist. `__range` and the drill-down domain stay ISO
(`:1248-1251`), so drill-down keeps working.

**The catch, which must not be glossed:** the *boundaries* are still Gregorian. A group labelled
"Bhadra" actually contains Bhadra 16 – Ashoj 15. That is arguably worse than an honest Gregorian
label, because it looks correct. **Route 2 should only ship together with Route 1, or not at all.**

## Smart-date input

`parse_date` (`tools/date_utils.py:108+`) implements Odoo's relative-date DSL —
`today`, `+1m`, `-2w`, weekday names, `=week_start`. The `m`/`y` offsets use
`dateutil.relativedelta` on **Gregorian** months, so a BS "+1 month" is not expressible in the DSL.

Any BS smart-date input must be resolved to an **absolute ISO date before it enters a domain**.

## Test matrix for when this is built

Per the brief, each against stored AD records:

| Case | Assertion |
|---|---|
| equals | a BS date selects exactly the records on that AD day |
| before / after | boundary day included/excluded correctly |
| between | BS range → the correct AD boundaries |
| **month** | a BS month selects **only** that BS month — the test that fails today |
| quarter | BS quarter boundaries, where a Nepali quarter is defined |
| year | BS year = Shrawan 1 → Ashar end, not Jan–Dec |
| **fiscal period** | matches `account.fiscal.year` exactly |
| group-by | group boundaries align with BS months, not merely the labels |

The month case is the acceptance test for the whole effort.

## Backlog entries

| ID | Item | Priority | Effort |
|---|---|---|---|
| BSF-1 | Declarative BS-month `customOptions` filters on the ~20 highest-value search views | P1 | M |
| BSF-2 | Patch `_getDateFilterDomain` + `_enrichItem` for global BS filter buckets | P2 | L |
| BSF-3 | Stored `bs_year_month` on the reporting models, grouped as an ordinary field | P1 | L |
| BSF-4 | BS labels on Gregorian buckets — **only alongside BSF-3** | P3 | M |
| BSF-5 | BS smart-date input resolved to absolute ISO before domain construction | P3 | S |
