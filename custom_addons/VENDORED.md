# Vendored third-party modules

Modules in this directory that were **not written here**. Copied in rather than
submoduled so the repository is self-contained and a clone reproduces the exact
code that was tested.

| Module | Version | Licence | Source | Copied |
|---|---|---|---|---|
| `account_financial_report` | 19.0.0.0.19 | **AGPL-3** | [OCA/account-financial-reporting @19.0](https://github.com/OCA/account-financial-reporting/tree/19.0/account_financial_report) | 2026-08-09 |
| `report_xlsx` | 19.0.1.0.2 | **AGPL-3** | [OCA/reporting-engine @19.0](https://github.com/OCA/reporting-engine/tree/19.0/report_xlsx) | 2026-08-09 |
| `date_range` | 19.0.1.0.0 | LGPL-3 | [OCA/server-ux @19.0](https://github.com/OCA/server-ux/tree/19.0/date_range) | 2026-08-09 |

Locally authored modules in this directory — `l10n_np`, `l10n_np_bs` — are LGPL-3
and are **not** covered by the notes below.

## Why these are here

Odoo Community ships the `account.report` schema but not its renderer, so
financial statements cannot be built on it (see `l10n_np/README.md`). These OCA
modules bring their own rendering — wizards plus QWeb and XLSX output — and
depend only on Community `account`.

They add, under **Invoicing → Reporting → OCA accounting reports**:

- General Ledger
- Trial Balance
- Open Items
- Aged Partner Balance
- Journal Ledger
- VAT Report

Verified against a posted 100,000 NPR invoice at 13% VAT in a scratch Nepal
company: Trial Balance rendered 113,000.00 Dr = 113,000.00 Cr, balanced.

**Still not provided by these modules:** Balance Sheet and Profit & Loss. Those
remain the genuinely Enterprise-only pair, or must be built as custom QWeb
reports over `account.move.line`.

## AGPL-3 — what it means here

Two of the three are AGPL-3, not LGPL-3. Practically:

- **Internal use is unrestricted.** Running them on your own server for your own
  company carries no obligation.
- **The network clause bites only if you modify them** *and* offer the modified
  version to third parties over a network. Then you must publish your changes.
- **Do not edit these modules in place.** If behaviour needs changing, write a
  separate module that inherits and overrides. That keeps your code yours and
  avoids triggering the clause.
- Licence files and copyright headers must stay intact. They have not been
  altered.

## Updating them

There is no package manager for Odoo modules. To take a newer version:

```bash
git clone --depth 1 -b 19.0 https://github.com/OCA/<repo>.git /tmp/<repo>
# replace the module directory, then:
venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> -u <module> --stop-after-init
```

Check the OCA repo's migration notes first — OCA modules occasionally change
model or field names between versions.

## Note on the copy

Two zero-byte files, `TypeError` and `domainFromTree`, were present in
`date_range` after cloning and were deleted. They are not referenced by the
manifest and appear to be stray artifacts.
