# Accounting Nepal integration

**The non-negotiable requirement: existing Accounting Nepal behaviour must not regress.** It has a
working test suite and real users; the migration is judged against it.

> **Done, as `19.0.1.1.0`.** Verified on a `TEMPLATE`-copy of the live database, which had the legacy
> checkbox switched **on** — the only state where the migration means anything. The live `odoo19`
> database was deliberately left untouched; the upgrade is the operator's to run.
>
> Result on the copy: `calendar_system` → `bs` for every company, digit style carried across, legacy
> group and legacy column both gone, module at `19.0.1.1.0`, and the full custom suite green.
>
> Two things below turned out to be wrong and are corrected in place: the group does **not** move to
> core, and the per-user opt-out detection was unnecessary.

## What Accounting Nepal owns today

| Component | File | Disposition |
|---|---|---|
| `BsDateViewMixin` — arch injection | `models/bs_accounting_dates.py:33-82` | **Deleted.** Superseded by the registry override |
| 13 model bindings, 20 field slots | `:85-175` | **Deleted.** Covered by the global default |
| `group_bs_accounting_dates` | `security/bs_date_group.xml:13-16` | **Deleted outright.** It does *not* move to core — see the correction below |
| `res.company.l10n_np_bs_digits` | `models/res_company.py:13-18` | **Moves to core** as `bs_digits` |
| Settings checkbox + digit selector | `models/res_config_settings.py:11-27`, `views/res_config_settings_views.xml:10-31` | **Rewritten** to point at core; the Nepal block stays where it is |
| `tests/test_bs_accounting_dates.py` (16 tests) | | **Deleted, not re-pointed** — see the correction below. Replaced by `test_bs_calendar_integration.py` (14) and `test_bs_migration.py` (11) |

Net effect: `l10n_np_accounting` **loses** ~150 lines of BS machinery and gains a dependency. It
keeps only what is genuinely Nepal-accounting-specific.

## Three cycle-blockers, and the fixes

A naive move of the mixin fails, because it reaches *upward* three times:

| # | Upward reference | Fix |
|---|---|---|
| 1 | `GROUP = 'l10n_np_accounting.group_bs_accounting_dates'` hard-coded (`:30`), read at `:51`, `:61` | ~~Define the group in core~~ — **no group at all.** The preference replaced it; see the correction below |
| 2 | `self.env.company.l10n_np_bs_digits` (`:52`, `:67`) — a field owned by `l10n_np_accounting` | Move the field to core; keep only the `related` settings mirror upstream |
| 3 | 13 `_inherit` bindings naming `account.*` and `l10n_np.*` models | Only the abstract mechanism is portable. With the registry override these bindings simply cease to exist |

Because the new mechanism is a **JS registry override**, blocker 3 dissolves entirely — there is no
per-model binding to relocate.

## Import-path compatibility

Three sites import `odoo.addons.l10n_np_bs.tools.bs`:

- `l10n_np_fiscal_year/wizard/generate_np_fiscal_year.py:39` and `:50` — production
- `l10n_np_bs/tests/test_calendar_ui.py:70` — test

A **one-line re-export shim** left in `l10n_np_bs/tools/bs.py` means `l10n_np_fiscal_year` is not
touched at all. Only `ad_to_bs`, `bs_to_ad` and `month_length` are actually used in production —
3 of the 7 public functions.

## Migration — preserving current behaviour

Today's group is granted to `base.group_user`, so BS is on for **every internal user**. Resetting
everyone to AD would be a visible regression, so:

```
migrations/19.0.1.1.0/pre-migration.py:
  if version is falsy:                        # fresh install, no old state
      return
  if group_bs_accounting_dates ∈ base.group_user.implied_ids:
      UPDATE res_company SET calendar_system = 'bs'
  carry l10n_np_bs_digits -> bs_digits
```

### Two corrections to the plan above

**1. The group does not move to core; it is deleted.** The plan said to define the group in core and
re-point `implied_group` at it. But core has no group — the per-user preference *replaced* the group
entirely, which is what makes per-user opt-out and a company default possible at all. Keeping a group
as well would mean two mechanisms gating one behaviour, and a user could satisfy one and not the
other. So the settings checkbox is gone and the Nepal block now shows core's `calendar_system`,
`bs_digits` and `bs_report_output` directly.

**2. Detecting individually-removed users was dropped, because there are none.** The plan called for
giving explicit `calendar_system = 'ad'` to anyone removed from the group. That rested on a
misreading: the group was granted via `implied_group` on `base.group_user`, and `has_group` returns
True for an implied group **regardless of direct membership**. An individual opt-out was therefore
never possible under the old mechanism, so no database contains that state. Code to find it would
have looked thorough and done nothing. (The new mechanism does support per-user opt-out — that is one
of the reasons for the change — but nobody can have used it yet.)

**Runs `pre`-migration, not post.** It reads the old group and the old company column, and both must
still be present and untouched; the module's data files are reloaded after.

**Tested against a database that actually had the group set** — a `CREATE DATABASE … TEMPLATE` copy of
the live one, where the checkbox was on. A migration verified only where the feature was off is
untested in the only state that matters.

The migration's *logic* is additionally tested as a plain function against synthetic rows
(`test_bs_migration.py`), because a real upgrade runs once against a database whose "before" state is
then gone — that verifies it exactly once and never again in CI. Both are needed: the scratch-database
run proves it works end to end, the unit tests keep proving it.

## Behaviour changes a user would notice

Stated honestly rather than buried:

| Change | Effect |
|---|---|
| **Coverage widens from 20 to ~177 fields** | The point of the exercise — but an accounting user who saw BS only on invoice dates will now see it on stock, purchase, HR and CRM dates too. Company-wide, this is what "platform capability" means |
| **Default numerals become Latin** | Today a hand-written `widget="bs_date"` and the calendar action both force Devanagari regardless of the company setting. Unifying on the setting, defaulting Latin, is a visible change for anyone relying on the inconsistency |
| **`datetime` fields start showing BS** | 94 fields that previously showed AD. Correct, and the reason the timezone fix precedes the rollout |
| **Per-user opt-out becomes possible** | Previously required editing `group_ids` |
| Reports gain BS | Previously Gregorian-only |

## Accounting correctness — the invariant

**Accounting correctness must never depend on a formatted BS string.** Nothing in the design lets a
BS value reach the ORM: the widget converts through `bsToAd` before any write, and domains are built
from ISO strings.

The regression suite must prove this rather than assume it:

- **ORM invariance** — create an invoice as a BS user and as an AD user; assert the raw PostgreSQL
  `date` columns are identical.
- Existing 16 BS-date tests still pass, re-pointed at core.
- VAT return, TDS certificate and loan schedule figures are byte-identical before and after.
- Fiscal-year generation is unaffected — it uses `bs_to_ad` server-side, which does not move.
- The five lock dates still enforce correctly; a BS-mode user cannot post into a locked period.

## Ordering

1. Bump module versions (prerequisite for any migration)
2. Build core, with the **timezone fix first**
3. Add the preference; migrate the group → company default
4. Switch on the registry override
5. Delete the local mixin and bindings
6. Re-point and run the 16 existing tests, plus the new invariance tests
7. Only then extend to reports

Steps 3 and 5 must not be combined: land the preference and prove behaviour is unchanged *before*
removing the old mechanism, so a regression is attributable to one change.

### One step was inserted, for a reason worth recording

Between 4 and 5, **the registry override had to be tested before the old mechanism could be deleted.**
The plan treated the override as done once written; it was not. When a test was finally pointed at the
*selection* — which widget a bare `<field/>` actually gets — the dispatcher raised
`OwlError: Invalid props` and **every date field failed to render for a BS user**. The primary path was
dead, and no test had touched it.

Had step 5 gone ahead on schedule, the working `_get_view` mechanism would have been deleted in favour
of one that did not work, on a database where the feature was live. The ordering principle the plan
already states — prove the new thing before removing the old — is exactly what caught it, and it
applies to *verified working*, not merely *written*.

### What actually shipped, in order

1. `nepali_calendar_core` built, timezone fix first — commit `c7a73ae8`
2. Dispatcher tested; three defects found and fixed, two of them in the tests — `b1494cc8`
3. Selection tested, which exposed the broken dispatcher — `ff3d8e23`
4. Only then: mixin, bindings, group and settings checkbox deleted; migration added
