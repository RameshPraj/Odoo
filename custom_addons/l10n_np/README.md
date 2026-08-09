# Nepal — Accounting (`l10n_np`)

**Status: SCAFFOLD. The structure is complete and verified. The content is not.**

Odoo ships 225 country localizations and **none of them is Nepal** — verified against
`ir_module_module`. This module fills that gap.

---

## What is verified working

Loaded into a throwaway company and rolled back — nothing was committed:

```
'np' template registered : True   → 🇳🇵 Nepal (country_code NP)
Nepal provinces loaded   : 7      → P1…P7
accounts created         : 46
taxes created            : 6
journals created         : 8
fiscal positions         : 2

required company properties resolved:
   account_sale_tax_id                   VAT 13%
   account_purchase_tax_id               VAT 13%
   transfer_account_id                   Liquidity Transfer
   account_journal_suspense_account_id   Bank Suspense Account
   income_currency_exchange_account_id   Foreign Exchange Gain
   account_stock_valuation_id            Stock Valuation
```

So: the wiring is right, every account Odoo requires exists, and the chart instantiates.

## What is NOT verified — the accountant's job

⚠️ **Nothing in the chart has been reviewed by anyone who files Nepali tax returns.**
The account codes, names and structure are a *plausible generic skeleton*, not Nepali
practice. Do not post transactions until this is signed off — changing a chart of accounts
after entries exist is painful and sometimes impossible.

### Checklist for the SME

| # | Item | File | Question |
|---|---|---|---|
| 1 | **Chart of accounts** | `data/template/account.account-np.csv` | Is 6-digit coding right for Nepal? Does the structure match what NFRS / the IRD expect? Which accounts are missing? |
| 2 | **Account groups** | `data/template/account.group-np.csv` | Do the code ranges match the intended chart? |
| 3 | **VAT rate** | `data/template/account.tax-np.csv` | 13% standard is assumed. Correct? Any reduced rates? |
| 4 | **Zero-rated vs exempt** | same | The distinction is modelled but the *scope* of each is a guess. Which supplies fall where? |
| 5 | **VAT accounts** | same | Output VAT → `200901`, Input VAT → `100401`. Is netting to a single control account preferred? |
| 6 | **Fiscal positions** | `data/template/account.fiscal.position-np.csv` | Domestic + Export only. Is an SEZ or import position needed? |
| 7 | **Provinces** | `data/res_country_state_data.xml` | Names and ISO codes P1–P7. Province 1 named *Koshi* — confirm current official naming |
| 8 | **VAT return** | *not yet built* | The IRD VAT return needs to be defined as an `account.report`. See below |
| 9 | **Withholding tax (TDS)** | *not yet built* | Nepal has TDS obligations. Not modelled at all |
| 10 | **Fiscal year** | *not set* | Nepal's fiscal year runs Shrawan–Ashad (mid-July to mid-July), **not** Jan–Dec. Must be configured on the company |

### Item 10 is the one people forget

Odoo defaults the fiscal year to the calendar year. Nepal's runs **Shrawan 1 – Ashad end**
(≈ 16 July – 15 July). Set `fiscalyear_last_day` / `fiscalyear_last_month` on the company,
or every financial report will cover the wrong period.

The sibling module `l10n_np_bs` already handles Bikram Sambat date display, so the two are
designed to be used together.

## Not yet built

| Missing | Why it matters | Effort |
|---|---|---|
| **IRD VAT return** as `account.report` | Statutory filing | Days — needs the official form layout from the SME. The `account.report` engine **is** in Community, so this is configuration, not code |
| **TDS / withholding** | Legal obligation on many payments | Medium — see `l10n_in`'s TDS data files for the pattern |
| Demo data | Testing convenience | Hours |
| Nepali translations | UI language | The `l10n_ne/` toolchain at the repo root already covers general UI |

## How to use it

```powershell
# install
venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> -i l10n_np --stop-after-init
```

Then in Settings → Accounting, pick **🇳🇵 Nepal** as the chart template on a company whose
country is Nepal. Activate the **NPR** currency first (Odoo ships all currencies inactive).

⚠️ A chart template can only be loaded into a company that has **no journal entries yet**.

## File map

| File | Purpose | Who edits it |
|---|---|---|
| `models/template_np.py` | Wires accounts to company properties via `@template('np')` | Developer |
| `data/template/account.account-np.csv` | **The chart of accounts** | **Accountant** |
| `data/template/account.group-np.csv` | Code-range groupings | Accountant |
| `data/template/account.tax-np.csv` | VAT definitions + repartition | **Accountant** |
| `data/template/account.tax.group-np.csv` | Tax groups | Accountant |
| `data/template/account.fiscal.position-np.csv` | Domestic / export mapping | Accountant |
| `data/res_country_state_data.xml` | 7 provinces | Accountant confirms naming |
| `data/account.account.tag.csv` | Tags for tax reporting | Developer + accountant |

## Editing notes for developers

Two traps this codebase has already hit:

1. **A double hyphen is illegal inside an XML comment** and invalidates the entire file.
   Odoo merges module XML, so one bad comment can break far more than this module.
   Use a semicolon or an em dash.
2. **Every account id referenced in `template_np.py` must exist in the account CSV**, or
   installation fails with a missing-xmlid error. Prune the chart and the wiring together.

Run the guard before installing:

```powershell
venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> --test-enable --test-tags /l10n_np --stop-after-init
```
