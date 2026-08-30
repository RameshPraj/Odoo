# -*- coding: utf-8 -*-
{
    'name': 'Interactive Financial Reports',
    'version': '19.0.1.2.2',   # 1.1.0 = OCA drill-down overlays and the
                              # aged-balance date fix (FIN-3);
                              # 1.1.2 = the aged-balance render assertion counts
                              # a per-row invariant instead of a live-data total
    'category': 'Accounting/Reporting',
    'summary': 'Click a figure in a financial report to reach the entries behind it',
    'description': """
Makes the HTML financial reports drillable and foldable.

Odoo core already turns any element carrying ``res-id`` + ``res-model`` +
``view-type`` into a link to that record
(``web/static/src/webclient/actions/reports/report_hook.js``). This module adds the
other half: an element carrying ``res-model`` + ``domain`` opens a *filtered list*,
which is what lets a total on a statement lead to the journal items that produced
it. It also folds account blocks so a long statement can be read at section level.

Both are wired from outside the report iframe, so nothing has to be bundled into
the rendered document and the PDF is untouched: the attributes are inert without
JavaScript, and the same QWeb template serves screen and paper.

Also repairs the drill-down in OCA's ``account_financial_report`` from the outside.
Those templates are AGPL-3 vendored code and ``custom_addons/VENDORED.md`` forbids
editing them in place, so the fixes are QWeb inheritance here.
""",
    # account_financial_report is a hard dependency, not an optional one: the
    # overlays inherit its templates by xmlid, so without it this module cannot
    # load at all.
    'depends': [
        'account_financial_statements',
        'account_financial_report',
        # Reached transitively already, but this module imports its
        # controller directly, so the dependency is declared rather than
        # assumed present.
        'report_xlsx',
    ],
    'data': [
        # Security first, as elsewhere in this repository.
        'security/oca_acl_overrides.xml',
        'report/oca_drilldown_overlays.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'account_reports_interactive/static/src/report_interactive.js',
        ],
        'web.assets_unit_tests': [
            'account_reports_interactive/static/tests/**/*',
        ],
    },
    'author': 'local',
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': True,
}
