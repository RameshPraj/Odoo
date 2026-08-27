# Accounting Nepal

Findings by ID in [`BACKLOG.md`](BACKLOG.md).

## Verdict

**Well-engineered, and currently unable to produce a correct statutory output.**

The design is genuinely good: jurisdiction values are editable records rather than constants, the
Odoo 19 idiom is used correctly throughout, and the module READMEs are honest about what has not
been signed off. But three of the four things an accountant would actually *use* it for were
broken at audit time — the financial statements could not render, the VAT return computes nil, and
a foreign-currency loan posts the wrong numbers.

None of these is a design failure. All three are a testing failure: **every one is covered by a
green test that exercises the wrong layer.**

> **Updated 2026-08-19.** The statements now render, and are interactive and printable — **FIN-2 is
> RESOLVED** (commit `153749a6`). The other two stand. Note the pattern this document identifies
> has since recurred twice more, which is the more useful finding than any individual defect:
> **FIN-3** (OCA's Aged Partner Balance could not render either, and its tests passed because they
> converted the offending value themselves) and the report tests in this very module, which called
> `_get_report_values` directly and so proved the arithmetic while the report had never once
> rendered.

## Relationship to standard Odoo Accounting

`Accounting Nepal` **extends** Community `account`; it does not replace it. The umbrella module
`l10n_np_accounting` (`application: True`) owns almost no domain logic — it arranges actions from
Community, OCA and the six local modules into one menu tree, and adds the small pieces Community
leaves unreachable (a Reconcile button over the public `reconcile()` engine, a Lock Dates editor
over the five `res.company` fields).

Removing it removes the menu, never data. That is the right shape.

The one place it crosses the line is **UPG-1**: `security/account_groups.xml` rewrites three
`res.groups` records **owned by `account`**. See [`ODOO_REVIEW.md`](ODOO_REVIEW.md).

## FIN-2 (P0) — the three financial statements cannot render · **RESOLVED 2026-08-15**

> Kept as written because the diagnosis below is correct and worth reading; only the
> tense is wrong. The fix went the *opposite* way to the one prescribed here — see the
> end of this section.

Odoo resolves a report's data model as `report.<report_name>`
(`odoo/addons/base/models/ir_actions_report.py:1121-1123`):

| Declared `report_name` | AbstractModel `_name` | Match |
|---|---|---|
| `account_financial_statements.report_balance_sheet_document` | `report.account_financial_statements.balance_sheet` | ✗ |
| `…report_profit_loss_document` | `…profit_loss` | ✗ |
| `…report_cash_flow_document` | `…cash_flow` | ✗ |

**Verified by execution:** `_get_rendering_context_model` returns `None` for all three, and
`_render_qweb_html` raises `QWebError`. The templates then dereference `wizard`, `assets` and
`section` — variables the fallback context never sets.

The module's stated purpose is to supply the Balance Sheet, P&L and Cash Flow that Community
cannot render (it ships the `account.report` schema without a renderer). **None had ever
worked.**

**Fix as prescribed (S):** rename the three `_name`s to match `report.<report_name>`, then add
`_render_qweb_html(...)` to the tests and assert the HTML contains "TOTAL ASSETS". One assertion
would have caught this.

**What was actually done, 2026-08-15 —** and the difference matters, because the prescription above
does not work. Renaming the models produces
`report_account_financial_statements_report_balance_sheet_document`, 65 characters, and Odoo derives
a table name from `_name` even for an `AbstractModel` and validates its length against PostgreSQL's
63-character identifier limit. `-u` fails outright. The two names are locked together, so the fix
went the other way: the **templates** were renamed to `balance_sheet` / `profit_loss` / `cash_flow`,
with `report_name` and `report_file` following, and the short model names kept.

The test half of the prescription was right and was done: `TestReportsActuallyRender` renders all
three through `_render_qweb_html` by both routes. A second defect surfaced on the way —
`_get_report_values` read `data['wizard_id']` unconditionally, which raised `KeyError` for a report
opened by URL, the very route the error page's own retry link uses.

## FIN-1 (P1) — VAT return computes every box as zero

The relation table `account_account_tag_account_tax_repartition_line_rel` holds **0 rows**
cluster-wide, and **0 journal items carry any tax tag**. Every box derives from tax tags, so every
box is nil.

> **This corrects the previous audit.** It concluded the template "wires them to nothing." That
> was wrong.

The template is **correct**. `account.tax-np.csv` column 12 is `repartition_line_ids/tag_ids`,
populated on the VAT 13% rows:

```
"VAT_S_NP_13",…,"base","invoice","S_13 Base","",…
"",           …,"tax", "invoice","S_13 Tax","l10n_np_200901",…
```

This is the tag-**name** form, resolved against `(applicability='taxes', country_id=<chart
country>)` by `chart_template.py:1294-1301` — the same form upstream `l10n_uk` uses. The eight tag
records carry matching names, `applicability='taxes'` and `country_id=base.np`. All verified.

**The live database is stale.** Odoo applies chart templates at **adoption**
(`try_loading` / `_load`), not on `-u`. A company that adopted the `np` chart before the tag data
landed has taxes materialised without repartition tags, and no module update will backfill them.

**Fix (M): a data migration, not a template edit.** Core's reload path is already tag-aware —
on a non-`force_create` reload it clears everything on an existing tax *except* `tag_ids`
(`chart_template.py:422-427`), precisely so tags can be backfilled without disturbing user edits.

**Fix the guarding test in the same change (TST-1, S).** `test_vat_return.py:81-83` skips when the
sale tax has no tags — i.e. it disables itself under exactly the condition that indicates the bug.
Verified firing today. Replace with an assertion and build the tax as a fixture.

## ACC-1 (P1) — loans post foreign-currency amounts as company currency

`currency_id` is user-settable (`loan.py:39`), exposed on the form under
`base.group_multi_currency` (`loan_views.xml:74`), and the schedule computes and rounds in it
(`:178`). But both posting paths — drawdown (`:286-297`) and instalment (`:371-396`) — build move
lines with **`debit`/`credit` only**. Those are company-currency columns. Neither `currency_id`
nor `amount_currency` is ever set.

A USD 100,000 loan in an NPR company posts **NPR 100,000**. The entry balances, so
`test_drawdown_entry_is_balanced_and_hits_the_liability` passes, and the ledger is silently wrong
by the exchange rate.

**Fix:** either add `currency_id` + `amount_currency` with proper conversion (**M**), or — safer
given the module's own "what this does not do" section — make `currency_id`
`related='company_id.currency_id', readonly=True` and drop it from the form, closing the hole
until real multi-currency support is written (**S**).

## ACC-2 (P1) — Balance Sheet omits prior-year unallocated earnings — **RESOLVED 2026-08-23**

An *Unallocated Earnings (prior years)* line now sits in the equity section, computed as P&L
since inception minus the current fiscal year. Kept **separate** from the Current Period Result
on purpose: combining them would balance the sheet while misstating this year's profit, and an
accountant reads the two as different things. Full account in `BACKLOG.md`.

`financial_statements.py:146-149` adds back the **current** fiscal year's result, while assets and
liabilities are cumulative since inception. Community posts no automatic year-end closing entry,
so income and expense accounts accumulate across years.

`difference = Assets − Liabilities − Equity − CurrentYearResult = Σ(prior years' P&L)`.

For any company past its first fiscal year without manual closing entries, the sheet does not
balance and a "difference" line appears on a statutory statement. `test_balance_sheet_balances`
posts only current-FY entries, so it passes. Odoo's own reports solve this with a separate
*Unallocated Earnings* line. **Fix (S)** plus a test that posts a prior-FY entry.

## ACC-3 (P1) — the Export fiscal position substitutes nothing — **RESOLVED 2026-08-23**

Fixed by linking each zero-rated tax to the 13% tax it replaces, in the template and by a
`19.0.1.2.0` migration for the existing chart. An export invoice now comes out `VAT 0% /
tax=0.00`; a domestic one still `VAT 13% / tax=130.00`. `try_loading` could not do it —
`chart_template.py:412-421` re-applies `original_tax_ids` only for taxes that do not yet exist
("Only add tax mappings containing new taxes"), so the migration writes the link directly. Full
account, including a claim of mine that a negative control disproved, in `BACKLOG.md`.


Odoo 19 expresses substitution on the tax side: `account.tax.original_tax_ids` says *what a tax
replaces* (`account_tax.py:102-114`). Both zero-rated NP taxes leave that column **empty**
(`account.tax-np.csv:10,14`), so applying the Export position **leaves VAT 13% on the line**.

Upstream contrast — every non-domestic `l10n_uk` tax names the domestic taxes it replaces.

**Impact:** exports invoiced at 13%. Over-collection, and a wrong VAT return. **Fix:** one cell
each (`VAT_S_NP_13`, `VAT_P_NP_13`) — the finding was exactly right — plus a migration, since a
chart template only applies at adoption. Already-billed exports are not corrected retrospectively.

**ACC-4 (P2), for the SME:** the Export position has `auto_apply=1` with **no** country and no
country group, so it auto-applies to every partner outside Nepal — including foreign **vendors**,
zero-rating import purchases. Nepali reverse-charge treatment on imported services would make that
wrong. (The related hazard I checked for does *not* exist: a partner with no country gets no
fiscal position at all, per `partner.py:274-275`.)

## Chart of accounts

43 accounts. Every `account_type` maps to a valid Odoo 19 selection; `id`, `name`, `code` and
`account_type` are populated on every row; `code_digits: '6'` matches the codes. Structurally
sound as far as Odoo is concerned.

Observations for the SME — **flagged, not judged**, since this audit has no standing to assess
NFRS/NPSAS conformance:

- **`tag_ids` is empty on all 43 rows.** No account-level tagging, so nothing can drive a
  tag-based report engine later.
- **ACC-5:** `Tax Receivable` is typed `asset_current` but sits in the 2xxxxx liability code
  block, and the account-group file assigns that range to "Tax Payable". Type and code disagree.
  Harmless today (the statements key on type, not code) but wrong on a code-ordered trial balance.
- One PPE account and one accumulated-depreciation account — insufficient for NFRS PPE class
  disclosure or for per-class asset profiles.
- No `asset_non_current` or `liability_credit_card` accounts exist, yet the statements and cash
  flow classify on those types; those sections will simply be absent.
- Only one `equity_unaffected` account; no separate current-year-earnings account, which is what
  ACC-2 depends on.
- **43 accounts is a skeleton, not a statutory chart.** The module manifest says exactly this. I
  concur with its own warning: do not post real transactions against it until signed off.

## Journals and fiscal configuration

`l10n_np` adds exactly one journal of its own — `Tax Adjustments` (`TA`, type `general`). The rest
(Sales, Purchases, Miscellaneous, Exchange Difference, Cash Basis, Bank, Cash) are inherited from
the root template, which is correct.

Two fiscal positions, both `auto_apply` — Domestic (Nepal) and Export/Zero-rated. See ACC-3/ACC-4.

**Country wiring is correct**: `'countries': ['np']` on the five Nepal-specific modules,
`account_fiscal_country_id: base.np`, and `country_id: base.np` on all three tax groups and all
eight tags. Deliberately absent on `l10n_np_bs`, `l10n_np_loan` and `account_financial_statements`
— all genuinely country-neutral. Those are correct calls.

## The "jurisdiction values are records" claim — verified, and it holds

The umbrella manifest claims every jurisdiction-specific value is an editable record. **I
verified it, and it is substantially true** — unusually well honoured for a localisation:

| Value | Where it lives |
|---|---|
| TDS rates, thresholds, effective dates, legal reference, accounts | fields on `l10n_np.tds.category`; **zero percentages in the source** |
| IRD VAT return layout | `l10n_np.vat.return.form` / `.box`, versioned with in-force dates |
| VAT 13% | a data row in `account.tax-np.csv`, not code |
| Loan rate, term, frequency, method, accounts | fields on `l10n_np.loan` |
| BS digit style | a company field |

Both the TDS and VAT modules ship with **empty** rate and form tables by design, and have tests
asserting so.

**One genuine exception (ACC-7, P3):** `SHRAWAN = 4` and `ASHAR = 3` in
`generate_np_fiscal_year.py:12-13` hard-code the Nepali fiscal-year boundary itself. It is set by
law and has been debated in Nepal; changing it would require a code change, which contradicts the
stated policy. It should be two company fields.

**ACC-6 (P2):** the TDS certificate sequence uses `%(range_year)s` — the **Gregorian** year — and
sets `company_id = False`, so all companies/tenants share one number series and the year rolls
over mid-Nepali-fiscal-year. Editable as a record, but wrong out of the box.

## Financial workflow test coverage

| Workflow | Covered? |
|---|---|
| Loan → instalment → journal entry | ✅ **Well covered.** 22 tests: balanced entries, principal/interest split, double-post guard, closing balance lands on exactly zero under all three methods. Best-tested area in the suite — but see ACC-1, which sits in the gap between "balances" and "correct" |
| Reconciliation | ✅ Covered, including a real offsetting pair |
| BS date widget / arch cache | ✅ Very well covered, including cross-user cache leakage |
| Invoice → tax → VAT box | ⚠️ **Nominally covered, actually skipped** (TST-1) |
| Balance Sheet / P&L / Cash Flow | ⚠️ Logic covered, **rendering never exercised** (FIN-2) |
| Period close → lock date | ⚠️ The wizard is well tested; **no test posts an entry into a locked period** and asserts refusal. The enforcement is assumed |
| Payment → TDS withholding → certificate | ✅ **Covered 2026-08-23** (TST-5). Eight tests drive `action_collect_lines` through a real posted payment carrying a real withholding line. It turned out the method could not run at all — it queried an AbstractModel with no table — so the `getattr(..., 0.0)` defaults were latent rather than active. Figures now correct; **layout** still needs an SME |
| Asset → depreciation → posting | ❌ **Not covered.** The integration that Nepali fiscal years drive depreciation boards — the stated rationale for `l10n_np_fiscal_year` — is asserted nowhere |
| Multi-currency | ❌ **Not covered**, and ACC-1 is the live bug behind the gap |

## Readiness

**Not ready for statutory use.** Four correctness items must close first — FIN-2, FIN-1 (+TST-1),
ACC-1 must be closed or the field removed. (ACC-2 and ACC-3 closed 2026-08-23.)

Beyond code, the SME sign-off register the project already tracks remains open: chart of accounts
per NFRS/NPSAS, TDS rates and thresholds, the IRD VAT form layout box by box, TDS certificate
layout, and depreciation classes. The modules' own READMEs state this plainly and correctly:
*post test transactions freely, file nothing.*
