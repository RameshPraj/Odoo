# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Nepal - TDS (Withholding Tax)',
    'version': '19.0.1.3.0',   # 1.1.0 = multi-company record rules (SEC-2);
                              # 1.2.0 = certificate collection fixed (TST-5)
                              # 1.2.1 = empty-database test assertions (TST-2)
                              # and indexes added (SCH-1)
    'countries': ['np'],
    'category': 'Accounting/Localizations',
    'summary': 'Configurable TDS rate schedule, certificates and return for Nepal',
    'description': """
Nepal - TDS (Withholding Tax)
=============================

Framework for Nepali withholding tax. Deduction itself reuses Odoo's own
``account.withholding.line`` from ``l10n_account_withholding_tax``; this module
adds the Nepal-specific layer around it:

* ``l10n_np.tds.category`` -- a rate schedule maintained by an accountant, with
  effective-from/to dates so a Finance Act change is a new record rather than a
  code change, and past returns still compute on the rate that applied then
* ``l10n_np.tds.certificate`` -- certificates issued to payees, populated from
  the posted withholding lines so they cannot disagree with the ledger
* ``l10n_np.tds.return`` -- periodic aggregation for filing

.. important::

   **This module ships with an EMPTY rate table, deliberately.**

   Nepali TDS rates, thresholds and exemptions are set by the Income Tax Act and
   amended by Finance Acts. They are not knowledge that belongs in source code,
   and a guessed rate produces wrong filings. An authorised user enters them
   under Accounting Nepal > Configuration > TDS Categories.

   The certificate layout is a placeholder pending confirmation of the statutory
   format. See README.md.
""",
    'depends': [
        'l10n_np',
        'l10n_account_withholding_tax',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/l10n_np_tds_rules.xml',
        'data/ir_sequence_data.xml',
        'views/tds_category_views.xml',
        'views/tds_certificate_views.xml',
        'views/tds_menus.xml',
    ],
    'author': 'local',
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
