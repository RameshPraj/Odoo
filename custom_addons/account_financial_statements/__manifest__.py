# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Financial Statements (Balance Sheet & P&L)',
    'version': '19.0.1.2.4',   # 1.1.0 = interactive drill-down and anomaly
                              # panel on the three statements (FIN-2);
                              # 1.2.0 = unallocated prior-year earnings on the
                              # balance sheet (ACC-2);
                              # 1.2.2 = cash-flow tests assert the delta the
                              # seeded movements cause, not period absolutes
    'category': 'Accounting/Reporting',
    'summary': 'Balance Sheet and Profit & Loss for Odoo Community',
    'description': """
Financial Statements
====================

Odoo Community ships the ``account.report`` schema but not its renderer, and
OCA's ``account_financial_report`` provides ledgers rather than statements. This
module adds the two missing statements directly over ``account.move.line``:

* Balance Sheet -- cumulative to a date, including the current period result so
  that it balances
* Profit and Loss -- for a chosen period, with gross and net profit

Sections are keyed on ``account.account.account_type`` rather than on code
prefixes, so the reports keep working when the chart of accounts is renumbered.

Reachable at Accounting > Reporting > Balance Sheet / P&L.
""",
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'report/financial_statements_templates.xml',
        'wizard/financial_statements_wizard_views.xml',
    ],
    'author': 'local',
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
