# Architecture

Findings by ID in [`BACKLOG.md`](BACKLOG.md).

## What this system is

An Odoo 19.0 **Community** deployment carrying a locally built Nepal accounting suite, intended to
become a **database-per-tenant SaaS**. Its purpose is to reproduce Odoo Enterprise Accounting
(proprietary, OEEL-1) using only LGPL/AGPL components, plus Nepal-specific statutory behaviour
Enterprise would not provide anyway.

## Repository shape

```
odoo-19.0/
├── odoo/                  51,775 tracked files  ← vendored upstream core (98.6%)
│   └── addons/            685 modules, 87 locally patched with i18n_extra/ne.po
├── custom_addons/         632 tracked files
│   ├── 8 locally written modules
│   └── 7 vendored OCA modules (4 of them AGPL-3)
├── l10n_ne/               91 files — translation toolchain, NOT an Odoo module
├── deploy/                systemd unit, Linux config, runbook
└── docs/project-review/   this audit
```

The 98.6 : 1.2 ratio is the defining architectural fact (SUP-1, SUP-4). It determines
upgradability, review ergonomics, clone cost, and roughly 95% of the cloud-sync exposure surface
in DAT-1.

## Module graph

```
                          account  (Odoo Community, LGPL-3)
                             │
     ┌───────────────────────┼────────────────────────┬──────────────┐
  l10n_np              l10n_np_bs            account_financial_   analytic
 (chart, VAT,      (Bikram Sambat,            statements          payment
  tags, taxes)      widget, calendar)        (BS / P&L / CF)      hr_expense
     │                       │                        │
     └────────┬──────────────┴────────────┬───────────┘
    l10n_np_fiscal_year            l10n_np_tds
    (Shrawan–Ashar)                l10n_np_vat_return
              │                    l10n_np_loan
              └───────────┬───────────────┘
                 l10n_np_accounting     ← application: True, the installable app
                          │
      vendored OCA: account_financial_report ── date_range ── report_xlsx
                    account_asset_management ── report_xlsx_helper
                    account_fiscal_year  (overridden by l10n_np_fiscal_year)
                    account_budget_oca
```

Two structural observations:

- **`l10n_np_accounting` is an assembly module.** It owns almost no domain logic; it arranges
  actions into one menu tree and adds the pieces Community leaves unreachable. Removing it removes
  the menu, never data. That is the right shape — and it is also where the licence weight lands
  (LIC-1) and where UPG-1 crosses into core.
- **AGPL reaches the app through four independent edges**, so no single dependency removal
  decouples it. The tightest coupling is `l10n_np_fiscal_year` *overriding* `account_fiscal_year`.

## Data flows

### VAT return — the statutory path, and where it stops

```
invoice posted
   └─ account.move.line   ← should carry tax tags via the tax's repartition lines
        └─ account.account.tag              ✗ 0 rows in the live relation (FIN-1)
             └─ l10n_np.vat.return.box       → every box computes 0
                  └─ l10n_np.vat.return.line (frozen against a versioned form)
                       └─ IRD return document
```

The design is sound: boxes are configurable records, forms are versioned, and a filed return
freezes the form it was computed against so a reprint cannot drift. The break is that the chart
was materialised before the tag data landed, and Odoo applies templates at **adoption**, not on
`-u`.

### Loan → ledger

```
l10n_np.loan (principal, rate, term, frequency, method, 4 accounts, currency_id)
   └─ _build_schedule()   EMI | equal-principal | interest-only
        │                 final instalment repays the residual → closing lands on exactly 0
        └─ l10n_np.loan.line × term
             └─ action_post() → account.move
                   Dr loan account (principal) / Dr interest / Cr bank
                   ✗ debit+credit only — no amount_currency (ACC-1)
```

Idempotency rests on an in-memory `state == 'posted'` check, which is **safe**: REPEATABLE READ
plus five-try serialization retry means a concurrent double-post loses on the row UPDATE, retries,
re-reads, and raises.

### Financial statements

Locally written QWeb reports keyed on `account_type` — Community ships the `account.report` schema
without a renderer, which is why the module exists at all. They **could not render** until
2026-08-15, because the report model naming did not match `report.<report_name>` (**FIN-2**, now
resolved).

They are now also **interactive and printable**: every figure carries the domain that produced it, so
clicking it opens exactly those journal items, and each statement has a `qweb-pdf` action sharing its
`report_name`. The drill-down is HTML attributes rather than a component, which is what lets one
template serve both the screen and the PDF — see `account_reports_interactive/README.md`.

### Bikram Sambat — the most runtime-invasive local code

```
Settings checkbox → implied_group → group_bs_accounting_dates
                                          │
account.move._get_view()  ← overridden in bs_accounting_dates.py
     │  walks the arch, sets widget="bs_date" on an allowlist of date fields
     └─ _get_view_cache_key() extended with (has_group, company digit style)
```

Correct, and a faithful copy of core's `res_currency` pattern. Storage stays Gregorian throughout
— the single decision that keeps domains, group-by, reporting and reconciliation unaffected.

Its limit is BS-3: the widget stops at `form` and `list`, and search/group-by buckets remain
Gregorian, so **every BS month is split** the moment anyone reports by period.

### Translations — the asymmetry that makes SUP-3 quiet

| Store | Source | Survives an Odoo upgrade? |
|---|---|---|
| **Model** translations (menus, labels) | jsonb columns in the database | **Yes** |
| **Code** translations (`_()`, `_t()`) | `.po` on disk, resolved by module path | **No** |

`l10n_ne` writes into `odoo/addons/<mod>/i18n_extra/`, genuinely the only location Odoo reads. An
upgrade therefore reverts code strings while model strings survive — a **half-Nepali UI**, harder
to notice than a clean revert.

## Current runtime

Single-process threaded server (`workers = 0`) on Windows, because gevent is unavailable there.
The Linux path (`deploy/`) is structurally different — systemd, multiprocessing, watchdog restored
— and shares **no build artefact** with dev (CI-2). It has never run.

The `limit_time_real = 0` divergence is legitimate and correctly reasoned: on Windows `reload()`
resolves to `TerminateProcess`, so the watchdog kills the server rather than reloading it. That is
documented and correctly reverted for Linux — but it must not ship to a shared instance (OPS-4).

## Recommended target architecture

Deliberately minimal, because tenant scale and instance model are undecided. Full reasoning and
the scale thresholds are in [`SAAS_MULTI_TENANCY.md`](SAAS_MULTI_TENANCY.md).

```
            ┌──────────────────────────────────────────────┐
  client ──►│ nginx / edge                                 │
            │  · TLS per tenant domain                     │
            │  · MUST pin X-Forwarded-Host      (SAAS-3)   │
            │  · MUST block /web/database/*  (SAAS-2, 10)  │
            └───────────────────┬──────────────────────────┘
                                ▼
            ┌──────────────────────────────────────────────┐
            │ Odoo instance (shard)                        │
            │  · dbfilter = ^%d$  anchored   (SAAS-1, 11)  │
            │  · list_db = False             (SAAS-6)      │
            │  · strong admin_passwd         (SAAS-2)      │
            │  · no smtp_* in odoo.conf      (SAAS-9)      │
            │  · limit_time_real = 120       (OPS-4)       │
            │  · cron allowlist, not all DBs (SAAS-7)      │
            └───────────────────┬──────────────────────────┘
                                ▼
                    PgBouncer (session mode)   ← required beyond ~50 tenants (SAAS-8)
                                ▼
            ┌──────────────────────────────────────────────┐
            │ PostgreSQL — one database per tenant         │
            │  · REVOKE CONNECT FROM PUBLIC     (PG-2)     │
            │  · REVOKE CREATE ON SCHEMA public (PG-4)     │
            │  · never superuser; never dblink in template │
            └──────────────────────────────────────────────┘
```

**Provisioning must** create the database through Odoo's own path (so `database.secret` is fresh —
this is what makes cross-tenant sessions impossible), apply both revokes, create a per-tenant
`ir.mail_server` with its own `from_filter` and bounce aliases, and register the tenant in the
edge routing map.

**Offboarding must** drop the database, remove the filestore directory, **purge that tenant's
sessions from the shared store**, revoke DNS and certificates, and apply the backup retention
policy. The session step is the one most likely to be forgotten, because the store is global.

## Architectural debts, ranked

1. **Vendored core in git** (SUP-1/SUP-4) — determines upgradability, review, clone cost and most
   of the sync exposure. Everything else is smaller.
2. **Patches inside the vendored tree** (SUP-3) — the upgrade path and the patch mechanism are in
   direct conflict, documented only in a docstring.
3. **Tenant routing is one regex** (SAAS-1/3/4) — no routing model, no tenant registry, no
   provisioning. This is the gap between "an Odoo instance" and "a SaaS".
4. **No deployment artefact** (CI-2) — dev and prod are related by prose, not by a build.
5. **Assembly module carrying licence weight and core modification** (LIC-1, UPG-1) — the app
   users install is where AGPL meets LGPL and where core records get rewritten.
