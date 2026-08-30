# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Accounting Nepal',
    # Bumped so migrations/19.0.1.1.0 runs: the Bikram Sambat group is
    # retired in favour of the calendar preference in nepali_calendar_core.
    'version': '19.0.1.4.2',   # 1.1.0 = accounting group ladder;
                              # 1.2.0 = app gated on accounting rights (SEC-12)
                              # and the group-wiring guard test (UPG-1);
                              # 1.3.0 = matching_status/matching_label and the
                              # Matching column widget;
                              # 1.4.0 = bank matching: clear an outstanding
                              # payment against a bank statement line, plus the
                              # first views for account.bank.statement.line;
                              # 1.4.1 = PG-2/PG-4 asserted by a test
    'countries': ['np'],
    'category': 'Accounting/Accounting',
    'sequence': 11,
    'application': True,
    'summary': 'Nepal accounting suite: chart, VAT, TDS, Bikram Sambat, fiscal year, statements',
    'description': """
Accounting Nepal
================

Umbrella module. Installing this pulls in the whole Nepal accounting suite:

* ``l10n_np`` -- chart of accounts, VAT 13%/0%/exempt, fiscal positions,
  tax tags, the 7 provinces
* ``nepali_calendar_core`` -- Bikram Sambat as a platform capability: a per-user
  calendar preference, every date field, date widget, browsable Nepali calendar,
  and BS on printed documents
* ``l10n_np_fiscal_year`` -- Shrawan-Ashar fiscal years generated from the
  Bikram Sambat calendar
* ``l10n_np_tds`` -- withholding tax: configurable rate schedule,
  certificates, return
* ``l10n_np_vat_return`` -- IRD VAT return from a versioned, configurable
  form definition
* ``account_financial_statements`` -- Balance Sheet, Profit & Loss, Cash Flow

Bikram Sambat
-------------
BS is no longer an accounting-only feature gated by a security group. It is a
per-user preference resolved **user -> company -> AD**, provided by
``nepali_calendar_core`` and covering every date field in Odoo. Set the company
default under Accounting Settings or General Settings; individuals override it in
their own Preferences.

Upgrading from 19.0.1.0.0 carries the old group across: if the "Bikram Sambat
accounting dates" checkbox was ticked, the company default becomes BS, so nobody
loses the calendar they were using.

Built entirely on Odoo Community (LGPL-3). No Enterprise module is used.

What this module does NOT do
---------------------------

It does **not** certify compliance with NFRS, NPSAS, the Income Tax Act 2058 or
the VAT Act 2052.

Every jurisdiction-specific value -- TDS rates and thresholds, the IRD VAT return
layout, depreciation rates -- is a **database record an authorised user edits**,
never a constant in source code. That is deliberate: those values are set by law
and amended by Finance Acts, so they must be maintainable without a developer,
and a wrong value must be correctable in minutes.

Consequently the suite ships with **empty rate and form tables**. A Nepali
chartered accountant must supply and sign off:

1. Chart of accounts structure per NFRS/NPSAS
2. TDS rates, thresholds, exemptions and effective dates
3. TDS certificate layout
4. IRD VAT return layout, box by box
5. Depreciation classes and rates, and whether pooled/block depreciation applies
6. Confirmation of VAT 13% and the scope of zero-rated versus exempt supplies

Until items 1-6 are signed off, treat the system as configured but not
authoritative: post test transactions freely, file nothing.
""",
    'depends': [
        'l10n_np',
        # The Bikram Sambat platform module. `l10n_np_bs` is now only a
        # backward-compatibility shim over it, so depend on the real one.
        'nepali_calendar_core',
        'l10n_np_fiscal_year',
        'l10n_np_tds',
        'l10n_np_vat_return',
        'l10n_np_loan',
        'account_financial_statements',
        # Referenced by the menu tree, so declared rather than assumed present.
        'account_financial_report',      # OCA: GL, TB, aged, open items, VAT report
        'account_asset_management',      # OCA: assets and depreciation
        'account_budget_oca',            # OCA: budgets
        'account_fiscal_year',           # OCA: explicit fiscal year records
        'analytic',
        'payment',
        'hr_expense',                    # Employee Expenses, as in the Invoicing app
    ],
    'data': [
        'security/account_groups.xml',
        'security/ir.model.access.csv',
        'security/oca_budget_acl_override.xml',
        'wizard/account_lock_dates_views.xml',
        'wizard/bank_matching_views.xml',
        'views/account_reconcile_views.xml',
        'views/account_bank_statement_line_views.xml',
        'views/account_aged_reports_views.xml',
        'views/res_config_settings_views.xml',
        'views/np_accounting_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # The Matching column widget. Two files, template after component,
            # matching the ordering convention in nepali_calendar_core.
            'l10n_np_accounting/static/src/matching_cell.js',
            'l10n_np_accounting/static/src/matching_cell.xml',
        ],
        # Declared so the hoot suite is compiled; it is *run* by
        # tests/test_js_unit.py, because declaring a bundle never executes it.
        'web.assets_unit_tests': [
            'l10n_np_accounting/static/tests/**/*',
        ],
    },
    'author': 'local',
    'license': 'LGPL-3',
    'installable': True,
}
