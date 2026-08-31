# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Nepal - Accounting',
    'version': '19.0.1.2.5',   # bumped per migration: 1.1.0 = FIN-1 tax tags,
                              # 1.2.0 = ACC-3 export substitution. Odoo runs a
                              # migration only when the version rises.
                              # 1.2.1 = lint fixes only, no new migration.
    'countries': ['np'],
    'category': 'Accounting/Localizations/Account Charts',
    'icon': '/account/static/description/l10n.png',
    'summary': 'Chart of accounts and VAT for Nepal',
    'description': """
Nepal - Accounting
==================

Odoo ships no Nepal localization: of the 225 country localizations in the
standard distribution, none covers Nepal. This module provides the missing
fiscal localization.

Activates:

- Chart of accounts
- VAT taxes (13% standard, 0% zero-rated, exempt)
- Tax groups and fiscal positions
- The 7 provinces of Nepal

.. warning::

   **This module is a SCAFFOLD, not a finished localization.**

   The structure, wiring and required-account coverage are complete and the
   module installs cleanly. The *content* -- account codes, account names, the
   VAT return layout -- is a minimal working skeleton that has NOT been reviewed
   by a Nepali accountant.

   Read ``README.md`` before using this on any real company. Do not post
   transactions against it until an accountant has signed off the chart, because
   changing a chart of accounts after entries exist is painful.
""",
    'depends': [
        'account',
    ],
    # Deliberately NOT auto_install: this must be a conscious choice while the
    # chart is unreviewed. Install explicitly with -i l10n_np.
    # NOTE: no account.report definitions here. Odoo Community ships the
    # account.report *schema* but not its renderer -- there is no _get_lines,
    # no get_options and no menu anywhere in Community. Report records would
    # install and then be unreachable. See README.md "Financial reports".
    'data': [
        'data/res_country_state_data.xml',
        'data/account.account.tag.csv',
    ],
    'demo': [],
    'author': 'local',
    'license': 'LGPL-3',
    'application': False,
    'installable': True,
}
