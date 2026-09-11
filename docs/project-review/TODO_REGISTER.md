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
| `l10n_np_accounting/README.md` | Bank reconciliation *screen* absent (engine + button present); `account_check_printing` available but not installed | **Partly closed** 2026-08-27. The one step a payment actually gets stuck on — clearing an outstanding payment against a bank statement line — is now built (`wizard/bank_matching.py`), along with the first `account.bank.statement.line` views in the codebase, since Community defines none. Still absent and deliberately so: match suggestions, batch matching, reconciliation models, statement import, and the statement header form (`account.bank.statement` is `create="false"` in Community with no form view). `account_check_printing` unchanged |
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

## ~~Lint suppressions without a linter~~ — QA-1, **RESOLVED 2026-08-23**

There is now a linter, and it reads them: `ruff.toml` and `.pylintrc` are committed and run by
`run-odoo.ps1 lint` / `run-odoo.sh lint`. Both are clean. 33 `# noqa` annotations remain across
local code, and they are now *enforced* annotations rather than folklore — ruff errors on an
unused one.

**The most consequential entry in the table below no longer exists.**
`vat_return.py:201`'s `# noqa: S307` suppressed "eval is dangerous" on a live `eval()`. **SEC-3**
was closed on 2026-08-23 by removing the `eval` entirely in favour of an AST walk, so the
suppression went with it — verified: neither `eval(` nor `noqa: S307` appears in that file.

That is the useful shape of this register: a suppression is a deferred decision, and closing the
finding underneath it should delete the suppression rather than leave it pointing at nothing.

*The original table, for context — note that the first two rows cite files that have since moved
or changed:*

| File:line | Suppression | Note |
|---|---|---|
| ~~`l10n_np_vat_return/models/vat_return.py:201`~~ **gone** | `# noqa: S307` | Suppressed "eval is dangerous" **on a live `eval()`**. Removed with the `eval` itself (**SEC-3**) |
| `l10n_np_bs/tools/bs.py:124` → now `nepali_calendar_core/tools/bs.py` | `# noqa: SLF001` | Acknowledges a private third-party symbol (**COD-10**, still open) |
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
| ~~Lint suppressions without a linter~~ | 33 | **QA-1 closed 2026-08-23** — ruff and pylint-odoo are configured, run by `lint`, and both clean. The suppressions are now enforced rather than decorative: ruff errors on an unused one |
