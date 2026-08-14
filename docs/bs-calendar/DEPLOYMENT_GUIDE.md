# Deployment guide

## Prerequisites

**1. Pin the Python dependency.** `nepali_datetime` is declared in `external_dependencies` but is
**absent from `requirements.txt`**. A fresh environment cannot install the suite at all — Odoo's
dependency check refuses `nepali_calendar_core`, and everything depending on it follows.

```
nepali-datetime==1.0.8.5      # pip name uses a hyphen; the import name uses an underscore
```

**2. Module versions.** ~~Everything is frozen at `19.0.1.0.0`~~ — **done.** `l10n_np_accounting` is now
`19.0.1.1.0` with `migrations/19.0.1.1.0/pre-migration.py`, which is what makes the upgrade fire at all.
`test_bs_migration.py::test_the_version_was_bumped` pins the two together, because a migration in an
un-bumped module sits on disk and never runs — and the first anyone would know is a user whose calendar
reverted.

**3. Take a backup and rehearse the restore.** The migration writes `res.company` and `res.users`.
Note that `res.company` writes are flushed through `cr.precommit` and can outlive `cr.rollback()`, so
a failed migration does not necessarily undo itself.

## Install order

```
1. nepali_calendar_core        (new)
2. l10n_np_bs                  -u   → becomes a shim
3. l10n_np_accounting          -u   → migration runs here
4. l10n_np_fiscal_year         unchanged (the shim covers its imports)
```

`-u` on `l10n_np_accounting` is what triggers the migration. Do it with the server **stopped**, then
start and verify before letting users in.

## What the migration does

```
migrations/19.0.1.1.0/pre-migration.py
  if not version:                                  -> return   (fresh install)
  if group_bs_accounting_dates ∈ base.group_user.implied_ids:
      UPDATE res_company SET calendar_system = 'bs'
  UPDATE res_company SET bs_digits = l10n_np_bs_digits
  (the group and the old column are then removed by the reload)
```

It does **not** write `res.users`. The plan called for detecting users individually removed from the
group and pinning them to AD; that state cannot exist, because `has_group` is True for a group implied
by `base.group_user` regardless of direct membership. So the migration touches one table, which also
makes the backup note above narrower than it was.

**Verified on a `CREATE DATABASE … TEMPLATE` copy of the live database, which had the checkbox on.**
That is the only state where the migration does anything. Result: `calendar_system='bs'` for every
company, digit style preserved, group gone, suite green.

### The visible change this causes

Worth saying to users *before* the upgrade, not after:

| | Before | After |
|---|---|---|
| Accounting dates (20 fields) | BS | BS |
| **All other business dates (~215)** | AD | **BS** |
| **Printed invoices, statements, certificates** | AD | **BS (AD)** — `bs_report_output` defaults to `both` |
| Numerals | Devanagari where hand-forced | the company `bs_digits` setting, default Latin |

If a narrower rollout is wanted, set `bs_report_output = 'ad'` **before** letting users in: screens
follow the preference while every outgoing document stays exactly as it is. Reports can be switched on
later, per company, without touching anything else.

## Post-deployment verification

Run in order; stop at the first failure.

| # | Check | Expected |
|---|---|---|
| 1 | `-u` completes with no `no such directory` or `ParseError` | clean |
| 2 | Full custom suite | **121 baseline tests + new, all green** |
| 3 | The 46,022-day selftest runs in CI | 0 mismatches |
| 4 | `SELECT calendar_system FROM res_company` | `bs` if the group had been set |
| 5 | Log in as a user who had BS | still sees BS — **no visible change** |
| 6 | A user who was removed from the group | sees AD |
| 7 | Open an invoice | `date`, `invoice_date`, `invoice_date_due` in BS |
| 8 | Open a stock picking | `scheduled_date` (a **datetime**) in BS, correct for the user's tz |
| 9 | `create_date` on any form | still **AD** — proves the exclusion list |
| 10 | Switch your own preference to AD, reload | AD immediately — proves cache invalidation |
| 11 | **ORM invariance** | create a record as BS user; raw SQL column identical to an AD user's |
| 12 | Export a list to CSV | **Gregorian**, byte-identical to an AD user's export |
| 13 | Print an invoice PDF | BS (or both) per the output-mode setting |
| 14 | Search filter "this month" | **still Gregorian buckets** — a known limitation, not a regression |

Check 10 is the one most likely to fail silently: if `calendar_system` was not added to
`_get_invalidation_fields`, the preference appears saved but nothing changes until restart.

## Configuration

| Setting | Where | Default |
|---|---|---|
| Company calendar | Settings → Nepal | `ad` |
| Numerals | Settings → Nepal | `latin` |
| Report output mode | Settings → Nepal | `both` |
| Per-user calendar | Preferences → Calendar | *follow company* |

Users set their own calendar from **Preferences**, without needing elevated rights.

## Rollback

| Layer | Action |
|---|---|
| Code | `git checkout` the previous commit; `-u` the affected modules |
| **Preference data** | The migration is **not automatically reversible** — it wrote `res.company` and `res.users`. Reverting the code leaves those fields populated but unread, which is harmless |
| Full revert | Restore the pre-deployment database backup |

To disable BS without uninstalling: set every company to `ad` and clear user overrides. The framework
stays installed and inert.

## Multi-tenant / SaaS

Nothing tenant-specific to configure. The preference is an ordinary per-database field and every cache
key is per-user or per-company. Deployment is per-database `-u`, the same as any other module.

The one cache that could have leaked across tenants — the lang-keyed, HTTP-public translations payload
— is avoided by design; the preference travels via `session_info` instead.

## Per-upgrade smoke test

There is **no upstream contract** for any of this: Odoo 19 has no alternate-calendar support, so every
seam is our own maintenance burden. After **each** Odoo major upgrade, verify:

| Seam | Check |
|---|---|
| `fields` / `formatters` / `parsers` registries | The `date`/`datetime` keys still exist and `force: true` still overrides |
| `standardFieldProps` | The widget's prop shape has not drifted |
| `session_info` | Still shipping `user_context` |
| `context_get` | Still the path into `env.context` |
| `_get_invalidation_fields` | Still the invalidation hook |
| `ir.qweb.field.date` / `.datetime` | `value_to_html` signature unchanged |
| Selftest | Still 0 mismatches — catches a `nepali_datetime` change |

Budget a day per major upgrade for this. If a registry key is renamed the symptom is silent: dates
revert to AD with no error.

## Known operational gaps at go-live

- **Search and group-by remain Gregorian.** Set expectations explicitly with BS users; this is where
  the localisation stops.
- **`wkhtmltopdf` is not installed**, so PDF output is unverified end to end.
- **The POS cashier UI** is not covered.
- **Exports stay Gregorian**, deliberately.
