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
| `account_financial_report` — `aged.partner.balance.report.wizard` | `account_reports_interactive/models/aged_partner_balance_report.py` | **The report could not render at all.** The wizard passes `date_at` as a `date` while the report calls `strptime` on it, so every Export raised `TypeError`. The override normalises it **on the report**, not the wizard: coercing the wizard broke two of the vendored module's own tests, which convert the value themselves (`test_aged_partner_balance.py:63,98`) and are the reason the defect stayed invisible. Finding **FIN-3**. Worth reporting upstream; an upstream fix supersedes this harmlessly. |
| `account_financial_report` — `report_open_items_ending_cumul` | `account_reports_interactive/report/oca_drilldown_overlays.xml` | Added amount-level drill-down, which the report had none of. Domains are built from the ids the report already selected (`Open_Items[...]`), because an open-items residual "as at" a past date is a function of reconciliation history and cannot be re-derived from `amount_residual`. |
| `account_financial_report` — `report_journal_ledger_journal_first_line` | `account_reports_interactive/report/oca_drilldown_overlays.xml` | Added drill-down on the journal debit/credit totals, which had none. Domains come from `journal['report_moves']` flattened through `move['report_move_lines']`, so they tie exactly to the printed total; a test asserts that. |

### Records of other modules that local modules overwrite

Not vendored code, but the same hazard: the record belongs to another module, so the
change **persists if ours is uninstalled**, and each needs a documented manual revert.

| Record | Owned by | Changed by | Revert |
|---|---|---|---|
| `account.group_account_readonly`, `..._user`, `..._manager` | `account` | `l10n_np_accounting/security/account_groups.xml` | clear the two `privilege_id` fields and remove the implication (**UPG-1**) |
| `mail.main_menu_discuss` | `mail` | `local_ui_tweaks/data/menu_tweaks.xml` | `env.ref('mail.main_menu_discuss').active = True` |

Both survive an upgrade of the owning module, because Odoo writes only the fields a
record actually lists and neither owner sets the field being changed. A tweak to a
field its owner *does* set would be reverted by any `-u` of that module. Verified for
the Discuss one by running `upgrade mail` and re-checking.

### One deviation that is edited in place, because it cannot be overridden

`date_range/tests/test_date_range.py`, `test_date_range_generator.py` and
`test_date_range_type.py` each gained `@tagged("-at_install", "post_install")` on
2026-08-19. Test tags are class decorators; there is no inheritance mechanism that
reaches them from another module, so an overlay is not possible here.

`date_range` is **LGPL-3**, not AGPL-3, so the network-copyleft reasoning above does
not apply — the only cost is that an update overwrites it.

**A second, smaller deviation, 2026-08-23:** the manifest version is now
`19.0.1.1.0` rather than upstream's `19.0.1.0.0`, so that Odoo's version comparison
can see the change above (**UPG-2**). Strictly this bump is not needed — the tag
change is pure Python and takes effect on restart — but `tools/check_module_versions.py`
flags any module whose files are newer than its version, and silently exempting one
module would defeat the check. Expect a conflict on the next upstream sync: take
upstream's version and re-bump.

**Why:** the module depends only on `web`, so it loads early, and `at_install` tests
run before `account` is in the registry. Their `setUp` creates a `res.company`, which
cascades a `res.partner` INSERT — and in any database that also has `account`,
`res_partner` already carries account's NOT NULL `autopost_bills` column
(`account/models/partner.py:608`) that the partial registry knows nothing about. 15 of
19 tests errored. Upstream CI never sees it because it installs only this module's
dependencies, so this is not an upstream bug and there is nothing to report.

**On upgrade:** re-apply the three tags. Without them the full suite goes from
`0 failed, 0 errors of 342` back to 15 errors, and
`docs/operations/ODOO_SERVICE_MANAGEMENT.md` says so at the point where somebody
running `test` would notice.

Also note `date_range` is **absent from the table at the top of this file** — that is
audit finding **DOC-3**, unrelated to this deviation but worth fixing in the same pass
as the rest of DOC-3.

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
