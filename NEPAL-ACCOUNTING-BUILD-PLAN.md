# Nepal Accounting Suite — Build Plan

**Status:** PLAN — no code written against it yet
**Supersedes:** `ENTERPRISE-ACCOUNTING-FINDINGS.md` (key evidence carried forward in §2)
**Lifecycle:** delete this file once §6 Phase D is deployed and accepted

---

## 1. The compliance boundary — read this first

This plan builds a **complete accounting system**. It does **not**, and cannot, certify
compliance with:

- Nepal Financial Reporting Standards (NFRS) / Nepal Public Sector Accounting Standards (NPSAS)
- Income Tax Act 2058 and its schedules
- Value Added Tax Act 2052 and IRD directives
- Any Finance Act amendment

**Why:** compliance is a legal determination, not an engineering one. Rates, thresholds,
depreciation classes and statutory form layouts are set by law and amended annually. I do
not have authoritative access to those texts, and encoding a wrong rate produces wrong
filings — a consequence that lands on the business, not on the software.

### How this plan handles it

| I build | A Nepali CA supplies |
|---|---|
| Models, wizards, reports, computation engines | The chart of accounts structure per NFRS/NPSAS |
| **Configurable rate tables** — never hardcoded | TDS rates, thresholds, exemptions |
| Statutory form **renderers** | The IRD form layouts, box by box |
| Depreciation **methods** | Which method the Act requires; classes and rates |
| Tests proving the arithmetic is correct | Sign-off that the arithmetic is the *right* arithmetic |

**Design rule, enforced throughout:** every jurisdiction-specific value is a database
record an accountant can edit. When a Finance Act changes a rate, nobody needs a developer.

**Acceptance rule:** no phase is "done" until its SME items in §7 are signed off. Code
passing tests is necessary, not sufficient.

---

## 2. Where we stand (evidence carried from the findings document)

### Enterprise comparison, measured on `aginmath.odoo.com` (`saas~19.4+e`)

108 modules installed — 52 OEEL-1 (Enterprise), 51 LGPL-3. Both `Invoicing` (`account`,
free) and `Accounting` (`accountant`, paid) exist as separate root menus; `accountant`
extends `account` rather than replacing it.

**The Enterprise instance had 25 `account.report` records. Localhost has 3** — Community
ships the report schema without the definitions or the renderer.

### Feature gap, localhost vs Enterprise

| Capability | Enterprise | Localhost today |
|---|---|---|
| Balance Sheet, Profit & Loss | ✅ | ✅ **built** (`account_financial_statements`) |
| Trial Balance, General Ledger | ✅ | ✅ OCA |
| Aged Receivable/Payable, Partner Ledger, Open Items | ✅ | ✅ OCA |
| Tax Report | ✅ | ✅ OCA + Community |
| Assets & Depreciation Schedule | ✅ | ✅ OCA |
| Budgets | ⚠️ not installed there | ✅ OCA |
| Audit Trail | ✅ | ✅ Community (hash chain) |
| **Cash Flow Statement** | ✅ | ❌ **Phase A** |
| **Executive Summary** | ✅ | ❌ Phase D (low value) |
| **Deferred revenue / expense** | ✅ | ❌ Phase C |
| **Bank reconciliation screen** | ✅ | ❌ Phase C |
| **Bank feeds** | ✅ | ❌ out of scope — paid third-party service |
| **Dunning / follow-ups** | ✅ | ❌ Phase D |
| Bikram Sambat dates | ❌ | ✅ **built** (`l10n_np_bs`) |
| Nepal chart of accounts | ❌ generic | ✅ **built, unreviewed** (`l10n_np`) |
| Shrawan–Ashar fiscal years | ❌ FY ends 31/12 | ✅ **built** (`l10n_np_fiscal_year`) |

**Decisive finding:** the Enterprise instance is configured `country=Nepal`,
`currency=NPR`, but `chart=generic_coa` and `FY ends 31/12`. **Paying for Enterprise did
not deliver a Nepal localization** — none exists at any tier. Both instances hold **zero
journal entries**.

### Already delivered

| Module | Provides | Tests |
|---|---|---|
| `l10n_np` | Chart of accounts, VAT 13%/0%/exempt, fiscal positions, 7 provinces | 7 |
| `l10n_np_bs` | Bikram Sambat conversion, date widget, calendar app | 13 |
| `l10n_np_fiscal_year` | Shrawan–Ashar fiscal years generated from BS | 8 |
| `account_financial_statements` | Balance Sheet, Profit & Loss | 9 |

Plus 7 vendored OCA modules (reports, assets, budgets) and Odoo's own withholding framework.

---

## 3. Scope

### In scope

1. Cash Flow Statement
2. Nepal TDS/withholding: configurable rate schedule, deduction at payment, certificates, return
3. IRD VAT return, driven by a configurable form definition
4. Nepal depreciation method (pooled/block) **if the Act requires it** — SME-gated
5. Deferred revenue and expense
6. Statutory report pack (annual statements in Nepali fiscal periods)
7. Bilingual presentation (English/Nepali) and Bikram Sambat dates on statutory output

### Out of scope

| Excluded | Reason |
|---|---|
| Bank feeds / online synchronisation | Paid third-party aggregator service, not a module problem |
| AI invoice capture | Paid metered service (Odoo IAP) |
| Rebuilding double-entry, reconciliation, tax engine | Already in Community and working; rebuilding adds risk, not value |
| Executive Summary dashboard | Low value; deferred to Phase D |
| Payroll | Separate domain, separate Act |
| Any claim of statutory certification | See §1 |

---

## 4. Architecture

Bridge-module pattern, matching Odoo's own convention: no module depends on another
except through a declared bridge, so any piece can be removed without breaking the rest.

```
                       Odoo Community `account`
                    (double entry, tax engine, ACLs)
                                  │
        ┌─────────────────┬───────┴────────┬──────────────────┐
        │                 │                │                  │
   l10n_np           l10n_np_bs   account_financial_    l10n_account_
   chart + VAT       BS calendar     statements         withholding_tax
   [BUILT]           [BUILT]         BS + P&L           TDS framework
        │                 │          [BUILT]            [Odoo core]
        │                 │                │                  │
        └────────┬────────┘                │                  │
                 │                         │                  │
      l10n_np_fiscal_year                  │                  │
      Shrawan–Ashar [BUILT]                │                  │
                 │                         │                  │
    ┌────────────┼─────────────┬───────────┴──────┬───────────┴────────┐
    │            │             │                  │                    │
l10n_np_vat   l10n_np_tds  l10n_np_          account_financial_   l10n_np_
_return       rates +      depreciation      statements           reports
IRD form      certs        pooled method     + Cash Flow          annual pack
[PHASE B]     [PHASE B]    [PHASE C]         [PHASE A]            [PHASE D]
```

### New modules

| Module | Depends on | Purpose |
|---|---|---|
| `account_financial_statements` *(extend)* | `account` | Add Cash Flow Statement |
| `l10n_np_tds` | `l10n_np`, `l10n_account_withholding_tax` | Rate schedule, certificates, TDS return |
| `l10n_np_vat_return` | `l10n_np` | IRD VAT return from a configurable form definition |
| `l10n_np_depreciation` | `l10n_np`, `account_asset_management` | Pooled/block depreciation — **only if required** |
| `account_deferred` | `account` | Deferred revenue and expense schedules |
| `l10n_np_reports` | all of the above | Annual statutory pack, bilingual, BS dates |

### Cross-cutting design rules

1. **Rates and thresholds are records, never constants.** A Finance Act change is a data
   edit.
2. **Group by `account_type`, not code prefix.** Reports survive the chart being
   renumbered during SME review. Already applied in `account_financial_statements`.
3. **Every statutory figure traces to journal items.** No derived number without a
   drill-down, or an audit cannot be answered.
4. **Bikram Sambat is presentation only.** Storage stays Gregorian; `l10n_np_bs` converts
   at the edge. Never persist BS dates.
5. **Every module ships an XML well-formedness test.** A malformed comment in one module
   blanks the entire web client — this codebase has already suffered it once.
6. **No module edits an OCA or Odoo module in place.** Inherit and override, so AGPL
   obligations are never triggered and upgrades stay clean.

---

## 5. Data model additions

### `l10n_np_tds`

| Model | Key fields | Notes |
|---|---|---|
| `l10n_np.tds.category` | code, name, rate, threshold, account, effective_from/to | **The SME fills this.** Date-bounded so historical rates survive a Finance Act |
| `l10n_np.tds.certificate` | partner, period, lines, total, sequence | One per vendor per period |
| `l10n_np.tds.return` | period, lines, totals | Aggregates for filing |

Deduction itself reuses `account.withholding.line` from Odoo core — no reimplementation.

### `l10n_np_vat_return`

| Model | Key fields | Notes |
|---|---|---|
| `l10n_np.vat.return.form` | name, version, effective_from, box_ids | **Versioned** — the form changes, old returns must still render |
| `l10n_np.vat.return.box` | code, label_en, label_ne, tax_tag_ids, formula | Maps IRD boxes to tax tags |
| `l10n_np.vat.return` | period, form_id, values, state | A filed return |

### `l10n_np_depreciation` *(conditional)*

| Model | Key fields |
|---|---|
| `l10n_np.depreciation.pool` | class code (A–E or as specified), rate, opening WDV |
| Extends `account.asset` | pool assignment, written-down-value method |

⚠️ Built **only** if the SME confirms pooled/block depreciation on written-down value is
required. If straight-line per asset is acceptable, OCA's module already suffices and this
module is cancelled.

---

## 6. Phases

Each phase is independently deployable and independently valuable.

### Phase A — Cash Flow Statement *(no SME dependency)*

Extends the existing `account_financial_statements`. Operating / investing / financing
sections classified by `account_type`, indirect method, opening and closing cash tie-out.

- **Effort:** ~1 day
- **Blocked by:** nothing
- **Acceptance:** closing cash on the statement equals the sum of `asset_cash` account
  balances at the end date, proven by test; statement reconciles to the Balance Sheet
  movement

### Phase B — TDS and VAT return *(SME-gated)*

Two modules, both built as empty configurable frameworks first, then populated.

- **B1** `l10n_np_tds` — models, deduction wiring, certificate and return renderers.
  Ships with an **empty** rate table and a loud warning until populated.
- **B2** `l10n_np_vat_return` — versioned form definition, box-to-tax-tag mapping,
  return renderer. Ships with **no** form definition until the IRD layout is supplied.
- **Effort:** ~4–6 days engineering, plus SME workshop
- **Blocked by:** SME items 2, 3, 4 in §7
- **Acceptance:** a filed return reproduces a manually prepared return for the same
  period, verified by the accountant, to the rupee

### Phase C — Depreciation and deferrals

- **C1** `l10n_np_depreciation` — **conditional**, see §5
- **C2** `account_deferred` — deferred revenue/expense schedules and recognition entries
- **Effort:** ~3–5 days, C1 conditional
- **Blocked by:** SME item 5
- **Acceptance:** a depreciation schedule matches the accountant's manual computation for
  a sample asset across a full fiscal year

### Phase D — Statutory pack and polish

- Annual report bundle in Nepali fiscal periods, bilingual, BS dates
- Executive Summary
- Dunning/follow-ups if wanted
- Bank reconciliation assist screen
- **Effort:** ~4–6 days
- **Blocked by:** Phases A–C accepted
- **Acceptance:** a full year-end pack produced from the system and accepted by the
  accountant

**On completion of Phase D acceptance, delete this file.**

---

## 7. SME input register — the actual critical path

Nothing in Phase B onward can start without these. Each maps to the file it lands in.

| # | Question | Lands in | Blocks |
|---|---|---|---|
| 1 | Chart of accounts per NFRS/NPSAS — structure, codes, names | `l10n_np/data/template/account.account-np.csv` | Everything downstream |
| 2 | TDS rates, thresholds, exemptions, and their effective dates | `l10n_np.tds.category` records | Phase B1 |
| 3 | TDS certificate format and mandatory fields | `l10n_np_tds` report template | Phase B1 |
| 4 | IRD VAT return layout, box by box, and which tax tags feed each box | `l10n_np.vat.return.form` records | Phase B2 |
| 5 | Depreciation: pooled/block or straight-line? Classes and rates? | `l10n_np_depreciation` or cancel it | Phase C1 |
| 6 | Confirm VAT 13% standard rate; scope of zero-rated vs exempt supplies | `l10n_np/data/template/account.tax-np.csv` | Phase B2 |
| 7 | Fiscal year confirmation: Shrawan 1 to Ashar end | already implemented — needs sign-off | Phase A reporting periods |
| 8 | Are Nepali-language statutory outputs mandatory or optional? | `l10n_np_reports` templates | Phase D |
| 9 | Retention and audit-trail requirements | configuration | Phase D |
| 10 | Which entity type — private company, NGO, public body? NPSAS applies differently | scoping of the whole chart | Everything |

**Recommended:** one 2–3 hour workshop with a Nepali CA covering items 1–7. That single
session unblocks Phases B and C entirely.

---

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Rates encoded wrongly** | Wrong filings, penalties | Rates are data, entered and signed off by the CA; never hardcoded |
| **Chart changes after entries exist** | Very expensive to correct | Sign off the chart **before** the first journal entry. Currently 0 entries — the cheapest moment |
| **Finance Act changes a rate mid-year** | Historical returns misstate | All rate records are date-bounded from day one |
| **Nepali fiscal year drift** | Wrong reporting periods | Already solved — fiscal years generated from BS, verified across 46,022 days |
| **OCA module upgrade breaks a bridge** | Reports fail | Never edit OCA in place; inherit and override; pin versions in `VENDORED.md` |
| **Vendor tree edits lost on upgrade** | Nepali translations disappear | Known issue: 87 `i18n_extra` files live in the Odoo tree. Move to a proper module before go-live |
| **Effort split across two instances** | Duplicate Nepal work | Decide localhost vs cloud **before** Phase B |
| **No CI** | Regressions reach users | Add a pipeline running `--test-tags` for all custom modules |

---

## 9. Decisions required before Phase B starts

1. **Which instance is the target** — localhost Community, or the paid Enterprise cloud?
   The Nepal work is identical on both, so running both doubles it.
2. **Entity type** (SME item 10) — determines whether NFRS or NPSAS governs the chart.
3. **Is the Enterprise subscription being kept?** If yes, Phases A, C2 and parts of D are
   redundant — Enterprise already ships Cash Flow, deferrals and dunning. **This plan is
   materially smaller if the answer is yes.**

---

## 10. Definition of done

- All modules install cleanly from a fresh database
- Every module has tests including XML well-formedness; full suite green
- No Enterprise module or code involved; every dependency LGPL-3 or AGPL-3, recorded in `VENDORED.md`
- All jurisdiction-specific values are editable records, not code
- A Nepali CA has signed off items 1–7 in §7
- One full fiscal year of sample transactions produces statements the accountant accepts
- `README.md` in each module states clearly what is verified and what is assumed

---

*Plan only. No code has been written against it. Supersedes
`ENTERPRISE-ACCOUNTING-FINDINGS.md`, whose evidence is carried forward in §2. Delete this
file once Phase D is deployed and accepted.*
