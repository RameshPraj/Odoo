# Vendored third-party modules

Modules in this directory that were **not written here**. Copied in rather than
submoduled so the repository is self-contained and a clone reproduces the exact
code that was tested.

| Module | Version | Licence | Source | Copied |
|---|---|---|---|---|
| `account_financial_report` | 19.0.0.0.19 | **AGPL-3** | [OCA/account-financial-reporting @19.0](https://github.com/OCA/account-financial-reporting/tree/19.0/account_financial_report) | 2026-08-09 |
| `report_xlsx` | 19.0.1.0.2 | **AGPL-3** | [OCA/reporting-engine @19.0](https://github.com/OCA/reporting-engine/tree/19.0/report_xlsx) | 2026-08-09 |
| `report_xlsx_helper` | 19.0.x | **AGPL-3** | [OCA/reporting-engine @19.0](https://github.com/OCA/reporting-engine/tree/19.0/report_xlsx_helper) | 2026-08-09 |
| `account_asset_management` | 19.0.1.0.2 | **AGPL-3** | [OCA/account-financial-tools @19.0](https://github.com/OCA/account-financial-tools/tree/19.0/account_asset_management) | 2026-08-09 |
| `account_fiscal_year` | 19.0.1.0.0 | **AGPL-3** | [OCA/account-financial-tools @19.0](https://github.com/OCA/account-financial-tools/tree/19.0/account_fiscal_year) | 2026-08-09 |
| `account_budget_oca` | 19.0.1.1.0 | LGPL-3 | [OCA/account-budgeting @19.0](https://github.com/OCA/account-budgeting/tree/19.0/account_budget_oca) | 2026-08-09 |

Also enabled: **`l10n_account_withholding_tax`** (LGPL-3) — not vendored, it was
already present in the Odoo tree and simply uninstalled. Provides the TDS
framework: `account.withholding.line`, `account.payment.withholding.line`,
withholding at payment registration.

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

## What currently overrides them

Kept here so an upgrade knows what to re-check. Nothing on this list edits a
vendored file; each is inheritance from a local module.

| Vendored target | Overridden by | What and why |
|---|---|---|
| `account_financial_report` — `report_aged_partner_balance_move_lines` | `account_reports_interactive/report/oca_drilldown_overlays.xml` | Eight report amounts were written `domain="…"` instead of `t-att-domain="…"`, so QWeb never evaluated the expression and emitted Python source text into the HTML attribute. The drill-down could not work. The overlay adds the `t-att-` form and removes the raw attribute; the expressions themselves are upstream's, unchanged. |

`account_reports_interactive` also patches core's `ReportAction` component to widen
report drill-down from single records to filtered lists. `account_financial_report`
patches the same component for the same purpose, so both hooks run; ours skips
elements already wrapped, and a test covers that. If upstream's hook is ever removed
or renamed, ours keeps working on its own.

**On upgrade**, re-check that the eight amounts are still eight and still in that
template. `account_reports_interactive/tests/test_oca_overlays.py` asserts the count
and asserts the vendored file still contains its original markup, so a version bump
that changes either fails loudly instead of silently dropping the fix.

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
