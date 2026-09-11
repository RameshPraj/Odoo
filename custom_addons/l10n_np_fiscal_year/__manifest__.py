# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Nepal - Fiscal Year (Shrawan to Ashar)',
    'version': '19.0.1.1.2',   # 1.1.0 = fiscal-year generation fixes
    'countries': ['np'],
    'category': 'Accounting/Localizations',
    'summary': 'Generate Nepali fiscal years as exact Gregorian date ranges',
    'description': """
Nepal - Fiscal Year
===================

Nepal's fiscal year runs **Shrawan 1 to Ashar end**, which in Gregorian terms
starts around 16-17 July and ends around 15-16 July. Because Bikram Sambat month
lengths vary from year to year, the Gregorian end date is not fixed:

    2080/81   2023-07-17 -> 2024-07-15   365 days
    2081/82   2024-07-16 -> 2025-07-16   366 days
    2083/84   2026-07-17 -> 2027-07-16   365 days
    2084/85   2027-07-17 -> 2028-07-15   365 days

Odoo's built-in ``fiscalyear_last_day`` / ``fiscalyear_last_month`` is a single
fixed pair, so it **cannot** express this. Explicit ``account.fiscal.year``
records are required, and this module generates them from the Bikram Sambat
calendar rather than by hand.

Everything that calls ``res.company.compute_fiscalyear_dates()`` then follows
the correct Nepali year -- including asset depreciation schedules, which
otherwise post on 31 December.

Usage: Accounting > Configuration > Generate Nepali Fiscal Years.
""",
    'depends': [
        'account_fiscal_year',   # OCA: explicit fiscal year records + override
        'l10n_np_bs',            # local: Bikram Sambat conversion
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/generate_np_fiscal_year_views.xml',
    ],
    'author': 'local',
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
