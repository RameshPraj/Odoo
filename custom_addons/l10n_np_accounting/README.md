# Accounting Nepal

Umbrella application. Installing this module pulls in the whole Nepal accounting suite and
presents it as one app: **Accounting Nepal**.

**81 menu items, 59 with actions**, mirroring the structure of the Enterprise Accounting
app but assembled entirely from Community, OCA and locally-built actions. No Enterprise
module is used.

## Menu parity against the Enterprise Accounting app

| Enterprise section | Here | Notes |
|---|---|---|
| **Customers** — Invoices, Credit Notes, Payments, Products, Customers | ✅ all 5 | Community `account` |
| **Vendors** — Bills, Refunds, Payments, Products, Vendors | ✅ all 5 | Community `account` |
| **Accounting → Transactions** — Journal Entries, Analytic Items | ✅ both | |
| **Accounting → Assets & Liabilities** — Assets, Loans | ⚠️ Assets ✅, **Loans ❌** | Loans is Enterprise-only; no OCA equivalent |
| **Accounting → Closing** — Reconcile, Tax Returns, Lock Dates | ⚠️ Bank Statements, VAT/TDS Returns, Secure Entries ✅ · **no reconciliation screen** | Reconciliation *engine* works from Journal Items; the drag-and-drop screen is Enterprise |
| **Review → Control** — Journal Items, Journal Audit | ✅ both | Journal Audit via OCA Journal Ledger |
| **Review → Audit** — Working Files, Annual Report | ❌ | Enterprise-only |
| **Review → Inventory** — Depreciation Schedule, Loans Analysis | ⚠️ Depreciation ✅ (OCA), **Loans Analysis ❌** | |
| **Review → Regularization** — Deferred Revenues, Deferred Expenses | ❌ | Phase C2 of the build plan, not yet built |
| **Review → Logs** — Audit Trail | ✅ | Community hash-chain audit trail |
| **Reporting → Statement Reports** — Balance Sheet, P&L, Cash Flow | ✅ all 3 | **locally built** (`account_financial_statements`) |
| **Reporting → Ledgers** — Trial Balance, General Ledger | ✅ both | OCA |
| **Reporting → Partner Reports** — Partner Ledger, Aged Receivable, Aged Payable | ✅ all | OCA + Community; Aged Rec/Pay is one combined wizard |
| **Reporting → Taxes & Fiscal** — Tax Report, Fiscal Report | ⚠️ VAT Returns (IRD) + TDS Certificates ✅ · **Fiscal Report ❌** | Nepal-specific returns replace the generic ones |
| **Reporting → Management** — Invoice Analysis, Analytic Report, Executive Summary | ⚠️ Invoice Analysis, Bills Analysis, Analytic Report, Budgets ✅ · **Executive Summary ❌** | Executive Summary is an Enterprise dashboard |
| **Configuration → Settings** | ✅ | |
| **Configuration → Accounting** — Chart of Accounts, Taxes, Journals, Currencies, Fiscal Positions, Checks, Depreciation Models, Return Types | ⚠️ 11 items incl. Tax Groups, Fiscal Years, Reconciliation Models, Multi-Ledger ✅ · **Checks ❌** (module available, not installed) · **Return Types ❌** (Enterprise) | |
| **Configuration → Invoicing** — Payment Terms, Product Categories | ✅ both, plus Incoterms | |
| **Configuration → Online Payment** — Payment Providers, Payment Methods | ✅ both | ⚠️ all 24 providers currently disabled |
| *(added)* **Configuration → Nepal Specific** | ✅ TDS Categories, VAT Return Forms | not in Enterprise — this is the Nepal layer |
| *(added)* **Nepali Calendar** | ✅ | Bikram Sambat browser |

### Genuinely missing, and why

| Item | Why |
|---|---|
| Loans / Loans Analysis | Enterprise-only; no Community or OCA equivalent exists |
| Bank reconciliation screen | Enterprise widget. The engine and auto-match rules work; reconcile from Journal Items |
| Deferred Revenues / Expenses | Phase C2 of the build plan; not yet built |
| Working Files, Annual Report | Enterprise audit-pack features |
| Executive Summary | Enterprise dashboard, low value |
| Fiscal Report | Enterprise; superseded here by the Nepal-specific VAT and TDS returns |
| Return Types | Enterprise |
| Checks | `account_check_printing` ships with Odoo but is not installed. Install it if cheque printing is needed |

## Nothing is duplicated

Every action in this menu already exists elsewhere; this module only arranges them. The
same records remain reachable from Odoo's own **Invoicing** menu. Removing this module
removes only the menu, never data.

## What this module does NOT do

It does **not** certify compliance with NFRS, NPSAS, the Income Tax Act 2058 or the VAT Act
2052. See the module description and `NEPAL-ACCOUNTING-BUILD-PLAN.md` §1.

Every jurisdiction-specific value is an editable record. The suite therefore ships with
**empty rate and form tables**, and a chartered accountant must supply:

1. Chart of accounts structure per NFRS/NPSAS
2. TDS rates, thresholds, exemptions and effective dates
3. TDS certificate layout
4. IRD VAT return layout, box by box
5. Depreciation classes and rates; whether pooled/block depreciation applies
6. Confirmation of VAT 13% and the scope of zero-rated versus exempt supplies

Until 1–6 are signed off: post test transactions freely, **file nothing**.
