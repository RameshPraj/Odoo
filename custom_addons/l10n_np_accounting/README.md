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

**Accounting → Configuration → Nepali Calendar**, or the same settings under
General Settings.

The calendar is a per-user preference resolved **user → company → Gregorian**, and
it is no longer specific to accounting: with Bikram Sambat selected, *every*
user-facing date field in Odoo displays BS, not a hand-maintained allowlist. A
second option chooses the numerals — Latin `2083-05-24` (default) or Devanagari
`२०८३-०५-२४` — and a third governs printed documents independently, so an invoice
does not change depending on who pressed Print.

**Dates are still stored as Gregorian `date` columns.** Nothing about domains,
group-by, sorting, reporting or reconciliation changes; only the rendering and
the accepted input do. `tests/test_bs_calendar_integration.py` asserts the stored
column directly, and `nepali_calendar_core` asserts it again against raw SQL.

The implementation lives entirely in `nepali_calendar_core`; this module only
surfaces the settings and depends on it. See
[`docs/project-review/BIKRAM_SAMBAT.md`](../../docs/project-review/BIKRAM_SAMBAT.md)
for the architecture.

> Earlier versions of this file described a security group plus a `_get_view`
> override that wrote `widget="bs_date"` onto an allowlist of 20 fields. Both were
> removed in `a80f8313`; the group became the calendar preference, and the arch
> injection became a registry override. The description is kept here only to
> explain what an upgraded database is migrating *from*.

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
| **Bank Matching** (Match to Bank / Bank Transactions) | A payment through an Outstanding Receipts/Payments account stays on the balance sheet until the bank confirms it. Community ships the engine, the "No Bank Matching" filter (`account_payment_view.xml:108`) and an index for that query (`account_payment.py:204`) — and nothing that acts on what the filter finds. `wizard/bank_matching.py` does the one step: resolve a bank statement line's counterpart onto the outstanding account and reconcile it against the payment. **This is not Enterprise's widget** — no match suggestions, no batch processing, no reconciliation models. See "Bank matching" below for what it will refuse and what must not be edited afterwards. |
| **Bank Transactions views** | Community defines **no view of any kind** for `account.bank.statement.line` (grep every `*.xml` under `odoo/addons`: zero hits), yet three core actions open that model — `account_payment.py:1200`, `company.py:518`, `account_move.py:5958` — and so land on ORM auto-generated views. `views/account_bank_statement_line_views.xml` defines the first list, search and form, which fixes those three screens too. |

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

## Bank matching

**Where it is.** *Accounting → Closing → Bank Transactions* lists statement lines, with a
**Match Outstanding Payment** button. A payment that is still waiting on the bank also carries a
**Match to Bank** button on its own form. Both open the same wizard; find the payments that need it
with Community's own **No Bank Matching** filter on the Payments list.

**Two ways to match.** *Match an existing bank transaction* when the statement has been entered or
imported — this is the correct workflow, because the transaction is a fact from the bank. *Record
the bank transaction now* when it has not, which asserts that the bank really did move the money;
the wizard says so on screen. If the statement is imported later, the transaction is already there
and must not be entered twice.

**What it refuses, and why.** Each refusal is a sentence naming what is wrong:

* a payment with no journal entry (still draft), or one already matched;
* a payment that posts straight to the bank, so it has no in-transit amount at all;
* an outstanding account not flagged *Allow Reconciliation*;
* **anything not in the company currency** — matching across currencies has to post the
  counterpart at the bank's rate rather than the system rate, which is separate work (ACC-1). It is
  refused rather than approximated;
* amounts that do not offset. This clears a payment **in full**; a bank amount that differs needs a
  write-off and has to be done by hand;
* a transaction already resolved onto another account, or on a different journal.

**Do not edit a matched transaction.** Six fields on a statement line — Label, Amount, Amount in
Currency, Foreign Currency, Currency and Partner — cause core to rebuild the journal entry
(`account_bank_statement_line.py:800-804`), which unlinks the matched line and therefore
**silently undoes the match**. `models/account_bank_statement_line.py` refuses those writes on a
matched line and tells you to press **Unmatch** first. Unmatch is this module's own, not core's
`action_undo_reconciliation`, because that method does `payment_ids.unlink()` — which would delete
the payment. Nothing here ever writes `payment_ids`; the payment ↔ transaction link is derived by
core from the reconciliation itself.

**Licence.** Independently implemented from LGPL-3 Community source only. The sequence it performs
is the one Odoo publishes in its own test suite — `account/tests/common.py:640-655` and
`test_account_payment.py:396-406`, the latter prefaced *"Reconcile without the bank reconciliation
widget since the widget is in enterprise."* No Enterprise source, screen or instance was read.

**Still absent.** Bank statements themselves remain uncreatable from their own list
(`account_bank_statement_views.xml:12` sets `create="false"`) and have no form view in Community.
Statement import is not built here either.

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
