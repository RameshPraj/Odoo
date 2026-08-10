# Accounting Nepal

Umbrella application. Installing this module pulls in the whole Nepal accounting suite and
presents it as one app: **Accounting Nepal**.

**87 menu items delivered to an administrator**, against 97 in the Enterprise Accounting
app, assembled entirely from Community, OCA and locally-built actions. No Enterprise module
is used.

## The permission gate you will hit first

In a stock Odoo 19 **Community** database, the **Accounting**, **Review** and **Reporting**
sections are invisible to every user, the administrator included. This is not a bug in this
module; the same thing happens in Odoo's own Invoicing app. The mechanism, in
`odoo/addons/account/security/account_security.xml`:

| Group | Community 19 | Enterprise 19 (`account_accountant`) |
|---|---|---|
| `group_account_readonly` | no `privilege_id` → cannot be selected on a user form | "Accounting / Read-only", selectable |
| `group_account_user` | no `privilege_id` → cannot be selected on a user form | "Accounting / Bookkeeper", selectable |
| `group_account_manager` | implies **`group_account_invoice` only** | implies **Bookkeeper** |

The menus are gated on `group_account_readonly` / `group_account_user`, and Community ships
no selectable role that grants either. `security/account_groups.xml` in this module closes
that gap using only records Community itself defines under LGPL-3: it gives the two groups
the existing Accounting privilege and makes Administrator imply Accountant. Nothing is
copied from Enterprise.

**Verify it the right way.** `ir.ui.menu.search()` does *not* apply menu group filtering, so
searching as a user returns menus that user can never see. Only `load_menus` filters. The
tests in `tests/test_menu_visibility.py` therefore assert through `load_menus`.

Two menu items stay hidden until you tick **Settings → Analytic Accounting**: *Analytic
Items* and *Analytic Report*. That gate is a normal Odoo setting and is correct behaviour.

## Bikram Sambat accounting dates

**Accounting → Configuration → Settings → Nepal → Bikram Sambat dates.**

With the checkbox on, accounting date fields are displayed and typed in Bikram
Sambat: the Accounting Date, invoice and due dates, delivery date, journal item
dates and maturity, payment dates, bank statement dates, the five lock dates, and
the period fields on the Nepal statements, VAT return and TDS return. A second
option chooses the numerals — Latin `2083-05-24` (default) or Devanagari
`२०८३-०५-२४`.

**Dates are still stored as Gregorian `date` columns.** Nothing about domains,
group-by, sorting, reporting or reconciliation changes; only the rendering and
the accepted input do. `tests/test_bs_accounting_dates.py` asserts the stored
column directly.

How it works, and why not view inheritance: `models/bs_accounting_dates.py`
overrides `_get_view` to set `widget="bs_date"` on an allowlist of fields, the
same seam core uses in `base/models/res_currency.py`. Gating with `group_ids` on
inherited views also works but needs one xpath per occurrence, and
`account.view_move_form` alone carries two `invoice_date` nodes and two
`delivery_date` nodes — a name-based xpath patches the first and silently misses
the rest. `_get_view_cache_key` is extended with both the group and the company's
digit style, otherwise the first user to open a form would fix the rendering for
everyone else.

Two caveats:

* The widget replaces the field's `options`, because options are widget-specific.
  On `invoice_date` that drops Odoo's `warn_future` hint, which warned when an
  invoice date was in the future.
* The group is granted through `base.group_user.implied_ids`, so the setting is
  database-wide for internal users rather than per user. Revoke the group from an
  individual user to give them Gregorian dates while others keep BS.

## Menu parity against the Enterprise Accounting app

Verified against a live Enterprise 19 instance (`account_accountant`, `account_reports`,
`account_asset`, `account_loans`, all OEEL-1) rather than against documentation.

Nearly every Enterprise report is an `ir.actions.client` served by `account_reports`
(OEEL-1) — Balance Sheet, P&L, Cash Flow, Trial Balance, General Ledger, Partner Ledger,
Aged Receivable/Payable, Tax Report, Fiscal Report, Executive Summary, Deferred
Revenues/Expenses, Journal Audit, Depreciation Schedule, Unrealized Currencies. That is why
they cannot simply be pointed at from Community: the renderer is the proprietary part. Where
this app provides the same statement, it is a locally written QWeb report, not a re-use.

| Enterprise section | Here | Notes |
|---|---|---|
| **Customers** — Invoices, Credit Notes, Payments, Products, Customers | ✅ all 5 | Community `account` |
| **Vendors** — Bills, Refunds, Payments, Products, Vendors | ✅ all 5 | Community `account` |
| **Accounting → Transactions** — Journal Entries, Analytic Items | ✅ both | |
| **Accounting → Assets & Liabilities** — Assets, Loans | ✅ both | Assets from OCA; **Loans built here** (`l10n_np_loan`). Registers only — the batch depreciation wizard moved to Closing |
| **Accounting → Closing** — Reconcile, Tax Returns, Lock Dates | ✅ all 3, plus Bank Statements and Secure Entries | **Reconcile** and **Lock Dates** are built here (see below) |
| **Review → Control** — Journal Items, Journal Audit | ✅ both | Journal Audit via OCA Journal Ledger |
| **Review → Audit** — Working Files, Annual Report | ❌ | Enterprise-only |
| **Review → Inventory** — Depreciation Schedule, Loans Analysis | ✅ both | Depreciation from OCA; **Loans Analysis built here** as a pivot over the schedule lines |
| **Review → Regularization** — Deferred Revenues, Deferred Expenses | ❌ | Phase C2 of the build plan, not yet built |
| **Review → Logs** — Audit Trail | ✅ | Community hash-chain audit trail |
| **Reporting → Statement Reports** — Balance Sheet, P&L, Cash Flow | ✅ all 3 | **locally built** (`account_financial_statements`) |
| **Reporting → Ledgers** — Trial Balance, General Ledger | ✅ both | OCA |
| **Reporting → Partner Reports** — Partner Ledger, Aged Receivable, Aged Payable | ✅ all 3 as separate items | OCA's one combined wizard, given two preset actions |
| **Reporting → Taxes & Fiscal** — Tax Report, Fiscal Report | ⚠️ VAT Returns (IRD) + TDS Certificates ✅ · **Fiscal Report ❌** | Nepal-specific returns replace the generic ones |
| **Reporting → Management** — Invoice Analysis, Analytic Report, Executive Summary | ⚠️ Invoice Analysis, Bills Analysis, Analytic Report, Budgets ✅ · **Executive Summary ❌** | Executive Summary is an Enterprise dashboard. Analytic items need Settings → Analytic Accounting |
| **Configuration → Settings** | ✅ | |
| **Configuration → Accounting** — Chart of Accounts, Taxes, Journals, Currencies, Fiscal Positions, Checks, Depreciation Models, Return Types | ⚠️ 11 items incl. Tax Groups, Fiscal Years, Reconciliation Models, Multi-Ledger ✅ · **Checks ❌** (module available, not installed) · **Return Types ❌** (Enterprise) | |
| **Configuration → Invoicing** — Payment Terms, Product Categories | ✅ both, plus Incoterms | |
| **Configuration → Online Payment** — Payment Providers, Payment Methods | ✅ both | ⚠️ all 24 providers currently disabled |
| *(added)* **Configuration → Nepal Specific** | ✅ TDS Categories, VAT Return Forms | not in Enterprise — this is the Nepal layer |
| *(added)* **Nepali Calendar** | ✅ | Bikram Sambat browser |

### Built here because Community ships the engine but no way to reach it

| Item | What was added |
|---|---|
| **Loans / Loans Analysis** | `l10n_np_loan` — loan register, amortisation schedule (EMI, equal principal, interest-only), drawdown and instalment postings that split principal from interest, and Loans Analysis as a pivot over the schedule. Enterprise's `account_loans` is OEEL-1. **Correction:** an earlier version of this file said "no Community or OCA equivalent exists". That was overstated — only the local database and installed modules had been searched, not OCA's repositories, and OCA does ship an `account_loan`. Whether a 19.0 port exists could not be confirmed (GitHub is unreachable from this machine). The local module is named `l10n_np_loan` precisely so OCA's can be installed alongside it. |
| **Reconcile** | `account.move.line.reconcile()` is public LGPL-3 code that does full and partial matching and raises exchange-difference moves; Community ships no button for it. `models/account_move_line.py` adds one, plus the precondition checks that turn a traceback into a sentence, and an action pre-filtered to posted items with a residual on reconcilable accounts. This is not the Enterprise drag-and-drop widget. |
| **Lock Dates** | All five lock dates live on `res.company` and are enforced on every posting by Community, but are only reachable buried in Settings. `wizard/account_lock_dates.py` puts them on one screen. Hard-lock irreversibility is left to core's own check in `account/models/company.py`. |

### Genuinely missing, and why

| Item | Why |
|---|---|
| Deferred Revenues / Expenses | `ir.actions.client` in `account_reports` (OEEL-1). Phase C2 of the build plan; not yet built |
| Working Files, Annual Report | Enterprise audit pack |
| Executive Summary | `account_reports` client action |
| Fiscal Report | `account_reports` client action; superseded here by the Nepal-specific VAT and TDS returns |
| Unrealized Currencies | `account_reports` client action (not previously listed; present in Enterprise) |
| Tax Units, Horizontal Groups, Fiscal Categories, Return Types, Accounting Reports, Online Synchronization | Enterprise configuration screens |
| Checks | `account_check_printing` ships with Odoo but is not installed. Install it if cheque printing is needed |

Enterprise's bank reconciliation *screen* is also absent; what is here is the engine plus a
button, which reconciles correctly but does not look like the Enterprise widget.

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
