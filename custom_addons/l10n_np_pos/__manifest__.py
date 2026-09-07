# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Point of Sale (Nepal)',
    'version': '19.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Optional customer on invoiced cash sales, and honest session journal items',
    'description': """
Point of Sale (Nepal)
=====================

Two corrections to stock Point of Sale behaviour, both reported from the live
till and both diagnosed against the database before being changed.

**A cash sale can be invoiced without selecting a customer.** Core requires one
whenever an order is flagged to-invoice. The requirement is relaxed, and the
configured **Walk-in Customer** is substituted on the invoice so it still
reconciles against its payment -- without a partner, core's receivable lookup
returns nothing and the invoice posts as permanently unpaid. Customer
requirements for *pay-later* methods and for presets needing a name or address
are deliberately left in place.

**A session's Journal Items now include the reversal.** Invoicing a PoS order
makes Odoo post the session closing entry, then reverse that entry's share for
the invoiced order, then issue the invoice. Core's related-moves query omitted
the reversal, so the screen showed revenue credited twice with nothing to explain
it. The books were always correct; the view was not.

Built on Odoo Community (LGPL-3). No Enterprise module is used.
""",
    'depends': ['point_of_sale'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'l10n_np_pos/static/src/customer_optional.js',
        ],
        # Declared so the hoot suite compiles; it is *run* by
        # tests/test_js_unit.py, because declaring a bundle never executes it.
        'web.assets_unit_tests': [
            'l10n_np_pos/static/tests/**/*',
        ],
    },
    'author': 'local',
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
