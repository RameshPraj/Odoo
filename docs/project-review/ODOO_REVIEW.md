# Odoo Review — patterns, ORM and upgrade safety

Findings by ID in [`BACKLOG.md`](BACKLOG.md). Supersedes the earlier `CODE_REVIEW.md`.

## Verdict

**This is one of the cleaner Odoo customisation codebases I have audited.** The upgrade-safety
posture is genuinely good and the discipline is visible in the source. Two things undermine it:
a data file that modifies core records, and the complete absence of migration scripts.

## What is clean — verified exhaustively

| Check | Result |
|---|---|
| Core Python or XML modified | **None.** `git log` over `odoo/` returns nothing but the 87 `i18n_extra` files |
| Monkeypatching (`Class.method = …` at import time) | **None** |
| `_sql_constraints` (silently ignored in 19) | **None** — migrated to `models.Constraint` in 8 places |
| `@api.one` / `@api.multi` | **None** |
| `attrs=` / `states=` in XML (removed in 17+) | **None** |
| `<tree>` instead of `<list>` | **None** |
| `name_get` | **None** |
| Legacy `Many2many` positional signature | **None** |
| `read_group` (deprecated in 19) in local code | **None** — all sites use `_read_group` |
| `@api.model_create_multi` on the one `create` override | **Present and correct** |
| Manifest `data` references that resolve | **All** |
| Version strings well-formed `19.0.x.y.z` | **All 15** |

`l10n_np_tds/models/tds_category.py:79-81` carries a comment explaining *why* the constraint
migration was necessary — that a legacy `_sql_constraints` list is silently ignored, so the check
would never reach the database. That is the difference between code that happens to work and code
someone understood.

## UPG-1 (P1) — core modification wearing a data costume

`l10n_np_accounting/security/account_groups.xml:32,39,49` writes:

```xml
<record id="account.group_account_readonly" model="res.groups">
<record id="account.group_account_user" model="res.groups">
<record id="account.group_account_manager" model="res.groups">
    <field name="implied_ids" eval="[(4, ref('account.group_account_user'))]"/>
```

These records belong to `account`, and they are **not** `noupdate`.

**Three consequences:**

1. **Silent revert on `-u account`** — including every 19.0.x point release. The reload drops
   `privilege_id`, `sequence`, the renames and the manager⇒user implication, and the Accounting /
   Review / Reporting menus vanish again for every user. Nothing detects it: the visibility test
   only passes right after a `-u l10n_np_accounting`.
2. **Not reverted on uninstall.** The module's own comment admits this. Uninstalling leaves core
   groups permanently mutated.
3. **Load-order fragility.** `implied_ids` uses the additive `(4, …)` command; if Odoo 20
   recomputes implications for `group_account_manager`, the link is dropped without error.

**Fix (S):** move to an idempotent `post_init_hook` that reapplies the values on every module
load, so an `account` update cannot silently undo them. Add a test asserting the implication
holds, and run it in CI *after* `-u account`.

Worth stating clearly: the *intent* is legitimate and well reasoned — Community genuinely leaves
those groups unreachable, which is what made the menus invisible. The problem is the mechanism,
not the goal.

## Private API usage

Complete inventory of calls into non-local private API, with a stability judgement:

| Call | Location | Risk |
|---|---|---|
| `_get_view()` override | `bs_accounting_dates.py:55` | **Medium.** Signature stable 16→19 and 8 core modules override it identically, but it is documented as an internal seam |
| `_get_view_cache_key()` override | `:45` | **Medium.** Introduced in 17; the contract (return `super()`'s key plus extra) is stable and used by `res.currency`, `res.partner`, `project.task` |
| `self._fields` introspection | `:71` | **Low.** Guarded, so a renamed field degrades gracefully |
| `_read_group(...)` | `vat_return.py:152`; `financial_statements.py:84`; `cash_flow.py:66` | **Medium-high.** Has changed shape in *every* recent major (17 replaced `fields=` with `aggregates=`; 18 changed result unpacking). No public alternative exists — `read_group` is itself deprecated. **Expect breakage at 20** |
| `nepali_datetime._days_in_month` | `bs.py:124` | **High, but non-Odoo.** Private function of an unpinned third-party package (COD-10, DEP-1) |
| `from …chart_template import template` | `template_np.py:14` | **Low.** The documented localisation extension point; ~200 upstream `l10n_*` modules import it identically |
| `wizard._fields[…].selection` **inside QWeb** | `financial_statements_templates.xml:42,132,221` | **Medium** (UPG-5). ORM internals in a template; `.selection` is a plain list only for statically-declared Selections. Prefer a computed field |

Not present, checked explicitly: `_reconcile_plan`, `_post`, `_compute_*` overrides on core
models, `odoo.tools` internals. `account_move_line.py:70` correctly calls the **public**
`lines.reconcile()`.

## The `_get_view` override — a faithful copy

`bs_accounting_dates.py` was compared line by line against core's own pattern in
`ir_ui_view.py:2978, 3064` and `res_currency.py:323-343`.

**Faithful:** signatures match core exactly, both `@api.model`; `_get_view` returns the
`(arch, view)` tuple and mutates `super()`'s result in place; `_get_view_cache_key` **appends** to
the returned tuple rather than rebuilding it; the `view_type not in ('form','list')` early return
mirrors `res_currency`. Keying on a group is sanctioned by `project.task`; keying on a company
field by `res_currency`. This override does both.

**Three minor deviations:**

1. Company resolution uses bare `self.env.company` where core uses
   `browse(context.get('company_id')) or self.env.company`. Cache correctness is preserved
   because both the key and the arch use the same expression, but a view fetched with an explicit
   `company_id` in context renders the wrong company's digit style. **NEEDS_VERIFICATION** in a
   multi-company session.
2. **BS-7** — `arch.iter('field')` walks embedded subviews of *other* models while the existence
   guard checks only the outer model's `_fields`. No collision exists today; a future non-date
   field named `date` in a nested subview would get `bs_date` applied, and Odoo only
   `console.warn`s on an unsupported field type before instantiating the widget anyway.
3. **UPG-7** — `_BS_DATE_FIELDS` is a plain class attribute, not `_inherit`-merged; a second
   module adding the mixin would silently lose one set.

**Verdict: I would not change the approach.** The rationale in its docstring — that
`account.view_move_form` carries two `invoice_date` nodes, so name-based xpath patches the first
and silently misses the second — is correct, and this is the best-engineered part of the codebase.

## View override fragility

Only **two** xpaths exist in the entire local codebase.

- **`//list[@name='move_line_tree']`, `position="inside"`** (`account_reconcile_views.xml:11`) —
  **low brittleness.** Name-based, single match, order-independent. This is the correct way.
- **`//block[@id='analytic']`, `position="before"`** (`res_config_settings_views.xml:10`) —
  **UPG-3, medium brittleness.** Sibling-relative, into `res_config_settings` — among the most
  churned arches in Odoo, where blocks are routinely renamed, merged or moved between modules. A
  rename produces a `ParseError`, which means **the module fails to install or upgrade**, not
  merely renders oddly. Target the containing ancestor with `position="inside"` instead.

No local module uses `//field[@name=…]` xpath anywhere — good, given the two-node problem above.

## Model extension

All `_inherit` usage is correct:

- Pure extension on `account.chart.template`, `account.move.line`, `res.company`,
  `res.config.settings`
- Mixin injection (`_name = X` **plus** `_inherit = [X, mixin]`) in 12 classes — the canonical
  idiom, correct in all 12
- `_inherits` (delegation) never used — correct, none of these models is a delegate
- No core `_name` redefined incorrectly

**UPG-4 (P3, POSSIBLE):** `account.lock.dates` is genuinely a new model — core ships
`account.lock_exception`, a different thing — but the name sits inside core's `account.`
namespace. If Odoo 20 introduces its own `account.lock.dates` (plausible; Enterprise already has
such a wizard), this module would silently *extend* it and the five precomputed fields would
collide. Rename to `l10n_np.account.lock.dates`.

## Migration readiness — UPG-2 (P2)

**Zero `migrations/` directories. All eight modules still `19.0.1.0.0`**, never bumped across
~15 feature commits including schema-changing ones.

**Consequence today:** because the version never changes, Odoo's "module is outdated" detection
never fires. `-u <module>` is the only way to apply changes, and a deploy that relies on version
comparison **skips these modules entirely**, leaving the database on old schema, views, menus and
**ACLs**. That makes it a correctness concern, not hygiene.

**What a 19→20 upgrade would do, per model:**

| Model | Data | Views |
|---|---|---|
| `l10n_np.loan` / `.line` | Survives — plain columns, core FKs only | Survive unless `account_type` selection values change (hard-coded in three domains) |
| `l10n_np.tds.*` | **Fixed 2026-08-23** — was querying `account.withholding.line`, an AbstractModel with no table, so the path could never run; now reads the persistent `account.payment.withholding.line` and the `getattr` defaults are gone (TST-5) | — |
| `l10n_np.vat.return.*` | Survives; `_read_group` is the highest-probability API break | — |
| Wizards | Transient — nothing to migrate. `account.lock.dates` at risk of name collision (UPG-4) | — |
| `l10n_np` chart | Materialised per company at adoption; template changes do **not** retro-apply — this is precisely FIN-1 | — |
| BS mixin consumers | — | **Highest blast radius.** If `_get_view`/`_get_view_cache_key` change in 20, every form and list load for `account.move`, `account.move.line`, `account.payment` and bank statements raises |

**UPG-6 (P3):** exactly two `noupdate="1"` files. The TDS sequence is correct (must not reset live
numbering). The provinces file is a trap: it is `noupdate` *and* self-flagged `NEEDS SME
CONFIRMATION`, so once an accountant corrects the names, the fix will **not** propagate to
existing databases. Plan a migration script for it.

## Duplication and dead code

| ID | What |
|---|---|
| COD-2 | `test_xml_is_well_formed` copy-pasted 5×, **missing from 3 of 8** modules; four copies use `minidom`, which accepts `--` inside comments where Odoo's `lxml` rejects it — so those four cannot catch the defect they exist for |
| COD-8 | Menu-tree walker written out three times in one file |
| COD-9 | "date_from precedes date_to" reimplemented four times, four messages |
| COD-3 | Three empty package directories on disk but untracked — `git clone` ≠ working copy |
| BS-1 | `tools/selftest.py` — working verification code that nothing runs |

COD-2 is the instructive one: four commits in the history are fixes for malformed XML blanking the
backend, the tests were written *after* being burned repeatedly, and copy-paste instead of a shared
mixin is exactly why three modules were missed and four copies use the wrong parser.

## Recommended sequence

1. **UPG-1** — move the group changes to a hook; add the post-`-u account` test. **S**
2. **UPG-2** — bump versions; add a release-checklist entry and ideally a CI check. **S**
3. **UPG-3** — re-anchor the settings xpath. **S**
4. **UPG-4** — rename `account.lock.dates` out of core's namespace. **XS**
5. **COD-2** — one shared `lxml` mixin across all eight modules. **S**
6. **UPG-5, BS-7, UPG-7** — small hardening of the `_get_view` override and the QWeb internals. **S**
