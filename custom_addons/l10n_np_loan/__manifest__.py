# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Loans',
    'version': '19.0.1.3.1',   # 1.1.0 = multi-company record rules (SEC-2);
                              # 1.2.0 = indexes on the columns those rules
                              # filter on (SCH-1);
                              # 1.3.0 = currency_id related to the company, so a
                              # loan can no longer be denominated in a currency
                              # its postings do not use (ACC-1);
                              # 1.3.1 = money compared through the currency and
                              # a clock-independent due test (COD-1, TST-6)
    'category': 'Accounting/Accounting',
    'summary': 'Loan register, amortisation schedule and instalment posting',
    'description': """
Loans
=====

A loan register with an amortisation schedule that posts to the ledger.

Enterprise's ``account_loans`` is licensed OEEL-1 and cannot be used here, so
this is written from scratch on Community ``account`` alone.

Deliberately named ``l10n_np_loan`` rather than ``account_loan`` so that OCA's
module of that name can be installed alongside it without a clash.

Three repayment methods
-----------------------
* **Equal instalment (EMI)** -- every payment identical, the principal/interest
  split shifting over time
* **Equal principal** -- principal in equal slices, so payments fall over time
* **Interest only** -- interest each period, whole principal at maturity

The final instalment repays whatever principal remains rather than a recomputed
figure, so the closing balance lands on exactly zero under any method, rate and
rounding.

Nothing is hard-coded
---------------------
Rate, term, frequency, method and every account are fields on the loan record.
Two loans from two banks on two rates are simply two records, editable by an
accountant without a developer.

What this does not do
---------------------
No penal interest, no moratorium or grace period, no floating rates tied to a
published base rate, no restructuring. A rate change must be recorded by closing
the loan and opening a new one.
    """,
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/l10n_np_loan_rules.xml',
        'views/loan_views.xml',
    ],
    'author': 'local',
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
