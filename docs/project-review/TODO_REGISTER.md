# TODO Register

Every deferred-work marker in the repository, with disposition.

## Headline: local code is clean, and that is misleading

**Zero** `TODO`, `FIXME`, `HACK` or `XXX` markers exist in any of the eight locally written modules
or in `l10n_ne/`. Verified across `*.py`, `*.js`, `*.xml`, `*.md`, `*.csv`, `*.scss`.

Genuinely good discipline — and also **DOC-5**: deferred work is real and substantial, it simply
lives in prose instead of code markers. Grepping the codebase for open work returns a false
all-clear.

---

## Deferred work not marked in code

The real open-work register. None of this is discoverable by grep.

| Source | Item | Disposition |
|---|---|---|
| `NEPAL-ACCOUNTING-BUILD-PLAN.md:261-273` | **SME sign-off register** — 9 open unknowns: chart per NFRS/NPSAS, TDS rates/thresholds/exemptions, TDS certificate layout, IRD VAT form box by box, depreciation classes and whether pooled/block applies, confirmation of VAT 13% scope | **Blocking for statutory use.** A go-live gate in [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md) |
| `NEPAL-ACCOUNTING-BUILD-PLAN.md:235-255` | **Phase C** (`l10n_np_depreciation`, `account_deferred`) and **Phase D** (statutory pack, bilingual output) not started | Open. Phase C1 was conditional on the SME confirming pooled/block depreciation, so it is blocked on the register above |
| `test_menu_integrity.py:23-27` | `KNOWN_ABSENT` — 7 Enterprise features deliberately not built: Deferred Revenues, Deferred Expenses, Working File, Annual Report, Fiscal Report, Executive Summary, Unrealized Currencies | **Best-managed deferred work in the repo.** A test asserts they stay absent and fails if one appears, forcing the README to be updated in the same commit |
| `l10n_np_accounting/README.md` | Bank reconciliation *screen* absent (engine + button present); `account_check_printing` available but not installed | Documented, intentional |
| `NEPAL-ACCOUNTING-BUILD-PLAN.md:3,5,255,321` | "delete this file once Phase D is accepted" | Open — but DOC-1 (the false status header) is far more urgent than deleting it |
| `deploy/README.md` | `wkhtmltopdf` provisioning | **Resolved on the dev host** 2026-08-15 — 0.12.6 patched-Qt installed under `.runtime/`, wired via `bin_path`, invoice PDF verified end to end. Still a go-live gate for the **server**, and `deploy/README.md` §1 now carries a Windows procedure. FIN-2 is separately resolved. Residual supply-chain risk tracked as **DEP-6** |
| `l10n_np/data/res_country_state_data.xml:10-12` | Province names self-flagged `NEEDS SME CONFIRMATION` | Open — and **UPG-6**: the file is `noupdate="1"`, so a later correction will not propagate to existing databases without a migration script |
| **Entire SaaS layer** | No tenant model, provisioning, offboarding, routing map, per-tenant backup or cross-tenant tests | The largest unmarked gap. Enumerated in [`SAAS_MULTI_TENANCY.md`](SAAS_MULTI_TENANCY.md) |

---

## Markers found — all in vendored OCA code

Fourteen occurrences, none authored here. **Do not fix in place** — editing vendored modules
destroys the zero-drift property protecting LIC-1.

| File:line | Marker |
|---|---|
| `account_financial_report/wizard/aged_partner_balance_wizard.py:134` | `# TODO: Kept for compatibility - To be merged into _prepare_report_data in 19` |
| `account_financial_report/wizard/general_ledger_wizard.py:291` | same |
| `account_financial_report/wizard/journal_ledger_wizard.py:97` | same |
| `account_financial_report/wizard/open_items_wizard.py:168` | same |
| `account_financial_report/wizard/trial_balance_wizard.py:253` | same |
| `account_financial_report/wizard/vat_report_wizard.py:86` | same |
| `account_asset_management/models/account_asset.py:1183` | `# TODO : add ir_cron job calling this method` |
| `account_asset_management/models/account_asset_profile.py:237` | `# TODO last profile in self is defined as default…` |
| `account_asset_management/readme/HISTORY.md:39,41` · `README.rst:113,115` | migration-script and re-implementation notes |
| `report_xlsx_helper/report/report_xlsx_abstract.py:68` | `- 'col_specs': cf. XXX` |
| `report_xlsx_helper/report/test_partner_report_xlsx.py:9` | `# TODO:` |

**Worth noting:** the six `account_financial_report` TODOs all say *"To be merged into
`_prepare_report_data` **in 19**"* — the OCA authors intended this cleanup for the very series
vendored here. Combined with **API-1** (a deprecated `read_group` call that every sibling call site
already migrated away from), this copy is **mid-refactor upstream**. Since provenance is a branch
URL rather than a SHA (**DEP-5**), there is no way to tell whether the fix has since landed.

---

## Lint suppressions without a linter — QA-1

Not TODOs, but deferred decisions in the same spirit: `# noqa` annotations throughout local code
with **no linter configured to read them**.

| File:line | Suppression | Note |
|---|---|---|
| `l10n_np_vat_return/models/vat_return.py:201` | `# noqa: S307` | Suppresses "eval is dangerous" **on a live `eval()`** — and the whitelist does admit a DoS (**SEC-3**). The most consequential suppression in the repo |
| `l10n_np_bs/tools/bs.py:124` | `# noqa: SLF001` | Acknowledges a private third-party symbol (**COD-10**) |
| `test_menu_integrity.py:74,91` | `# noqa: BLE001` | Broad exception catch |
| 6 further sites | `# noqa: PLC0415` | Import inside function |

Ruff was clearly run once and its output annotated; the configuration was never committed, and
`.gitignore:11` ignoring `.ruff_cache/` corroborates ad-hoc use. Committing a matching config
turns these from folklore back into enforced decisions.

---

## Disposition summary

| Category | Count | Action |
|---|---|---|
| Markers in local code | **0** | None needed |
| Markers in vendored OCA | 14 | Leave in place; track upstream |
| Unmarked deferred work (prose) | 8 clusters | 2 block statutory use (SME register, `wkhtmltopdf`); the SaaS layer is the largest |
| Lint suppressions without a linter | 10 | Fold into QA-1 |
