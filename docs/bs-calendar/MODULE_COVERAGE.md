# Module coverage matrix

Discovered from the **live database** (134 installed modules), not from the brief's wish list.
Field counts exclude `create_date`/`write_date` and technical models.

**"BS Support" is stated as of *before* this pass, and has not been re-marked.** Nothing is marked
supported that has not been verified, per the brief's rule — and that rule is what stops this table
being updated now.

> The registry override that would move most of these rows to *Planned → Supported* is written, but
> its **selection** logic is not yet tested (BSD-9): the exclusion predicate is verified, and BS
> rendering is verified, but nothing yet asserts that a bare `<field name="…"/>` on a given model
> picks the BS widget. Marking a module supported on that basis would be exactly the "mark a module
> supported without testing it" the brief prohibits.
>
> The per-module sweep is **BSV-2**, and it is the work that earns the *Tested* column. Until then
> these rows stand as written.

## Legend

| Value | Meaning |
|---|---|
| **None** | No BS anywhere |
| **Partial** | Some fields, form/list only |
| **Planned** | Covered by the registry override once Phase 4 lands |
| **Deferred** | Needs search/group-by or calendar work — backlogged with a design |
| **N/A** | Module not installed, so no claim is made |

## Not installed — no coverage claimed

The brief asks for these; they are **not in this database**, so they are out of scope and
deliberately unmarked rather than assumed:

| Module | State |
|---|---|
| `project` (Projects: start dates, deadlines, milestones) | **UNINSTALLED** |
| `hr_holidays` (Time Off) | **UNINSTALLED** |
| `hr_attendance` (Attendance) | **UNINSTALLED** |
| `hr_recruitment` (Recruitment) | **UNINSTALLED** |
| `maintenance` (Maintenance dates) | **UNINSTALLED** |
| `hr_appraisal` (Appraisals) | **UNINSTALLABLE** |
| Payroll | not present in Community |

If any is installed later it is covered automatically by the registry override — that is the point
of the global mechanism — but it will need a row here and a test before being called supported.

## Installed modules

| Module | Date areas | BS Support | Required change | Priority | Tested |
|---|---|---|---|---|---|
| **`account`** (33 fields) | invoice/accounting/due dates, journal entries, payments, statements, lock dates, fiscal periods | **Partial** — 20 fields via the allowlist | Drop the local mixin; inherit the global default. Keep the model bindings | P1 | Yes — regression suite exists |
| **`stock`** (22) | scheduled, effective, deadline, `date_done`, reservation, lots, inventory adjustments, replenishment, orderpoint snooze | **None** | Registry override (automatic) | P1 | No |
| **`crm`** (13) | lead `date_deadline`, `date_closed`, `date_conversion`, `date_open`, activity report | **None** | Automatic. `crm.activity.report` is a **report model** → group-by, deferred | P2 | No |
| **`hr`** (12) | employee `birthday`, `visa_expire`, work-permit expiry; `hr.version` contract start/end, trial end, passport expiry | **None** | Automatic | P2 | No |
| **`account_asset_management`** (12) | asset dates, depreciation board | **None** | Automatic | P2 | No |
| **`account_financial_report`** (12) | report wizard date ranges | **None** | Automatic for the wizard fields. Report **output** is now mostly BS via the global QWeb converter; what remains is the templates that bypass `t-field` — see the rescoped **BS-8** | P2 | No |
| **`hr_skills`** (9) | certification / skill validity | **None** | Automatic | P3 | No |
| **`mrp`** (9, all `datetime`) | MO `date_start` / `date_finished` / `date_deadline`, work orders, workcentre productivity | **None** | Automatic — **all `datetime`, so timezone-dependent** | P2 | No |
| **`purchase`** (8) | RFQ/order date, `date_approve`, `date_planned` (expected arrival), purchase report | **None** | Automatic; `purchase.report` → group-by, deferred | P1 | No |
| **`point_of_sale`** (11) | `date_order`, session start/stop, payment date, shipping date | **None** | Automatic for back-office. **The POS UI is a separate frontend bundle — not covered** | P3 | No |
| **`l10n_np_tds`** (7) | TDS certificate and return periods | **Partial** — via the allowlist | Inherit the global default | P1 | Yes |
| **`base`** (6) | partner-level dates | **None** | Automatic | P3 | No |
| **`calendar`** (6) | event `start` / `stop`, `start_date` / `stop_date`, recurrence `until` | **None** | Fields automatic. **Calendar grid: BS labels only — a BS-bounded month view is a fork** | P2 | No |
| **`sale`** (5) | order date, `commitment_date`, `validity_date`, `signed_on`, sale report | **None** | Automatic; `sale.report` → group-by, deferred | P1 | No |
| **`l10n_np_accounting`** (5) | lock dates, statement wizard | **Partial** | Becomes the consumer of core | P1 | Yes |
| **`account_budget_oca`** (5) | budget periods | **None** | Automatic | P3 | No |
| **`date_range`** (5) | generated ranges | **None** | Automatic | P3 | No |
| **`l10n_np_vat_return`** (4) | VAT return period | **Partial** | Inherit the default | P1 | Yes |
| **`hr_expense`** (4) | expense date, approval date, accounting date | **None** | Automatic | P2 | No |
| **`product`** (4) | product-level dates | **None** | Automatic | P3 | No |
| **`stock_account`** (4) | valuation dates | **None** | Automatic | P3 | No |
| **`purchase_stock`** (3) | planned dates | **None** | Automatic | P3 | No |
| **`website`** (3) | `date_publish`, visitor tracking | **None** | **Exclude** visitor/tracking as technical. Portal-facing dates need `web.assets_frontend`, which does **not** inherit backend | P3 | No |
| **`mail`** (12) | activity `date_deadline` | **Mostly excluded** | Only `mail.activity.date_deadline` is user-facing; the rest are internals | P3 | No |
| `l10n_np`, `l10n_np_loan`, `l10n_np_fiscal_year`, `account_financial_statements` | chart, loan schedule, fiscal years, statement wizards | **Partial** | Inherit the default | P1 | Yes |

## Totals

| | Count |
|---|---|
| Stored date/datetime fields in the database | 1,223 |
| …`create_date` / `write_date` (excluded) | 961 |
| …other technical (excluded) | ~26 |
| **Business date fields in scope** | **237** |
| …`date` — timezone-free | 143 |
| …**`datetime`** — timezone-critical | **94** |
| Rendered in **form or list** — covered by the registry override | **177** |
| Rendered in **search** views — deferred | 22 |
| Rendered only in kanban / pivot / graph / activity | 5 |
| **Covered today** | **20 (1.6%)** |

## What "Planned" actually buys

The registry override is global, so a module needs **no code** to gain BS — which is why almost
every row above says "automatic". That is the point of the architecture, and also the reason this
matrix must be re-verified per module before any row is marked **Tested**: automatic coverage is
not the same as verified coverage.

Three categories remain uncovered after Phase 4, backlogged with designs rather than left implicit:

1. **Search filters and group-by** (22 fields, plus every report model). Group boundaries are
   computed server-side and BS months are not expressible as a `relativedelta` — see
   [`SEARCH_AND_FILTERS.md`](SEARCH_AND_FILTERS.md).
2. **The calendar month grid** — labels are patchable, boundaries are not.
3. **The POS point-of-sale UI** — a separate frontend bundle with its own rendering.
