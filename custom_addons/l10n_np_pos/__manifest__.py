# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Point of Sale (Nepal)',
    'version': '19.0.4.0.1',
    'category': 'Sales/Point of Sale',
    'summary': 'Walk-in cash sales are not stranded in invoice mode, and honest session journal items',
    'description': """
Point of Sale (Nepal)
=====================

Two corrections to stock Point of Sale behaviour, both reported from the live
till and both diagnosed against the database before being changed.

**Clearing the customer now clears the invoice request.** Core sets
``to_invoice`` implicitly whenever the chosen customer is a *company*, and
nothing ever resets it -- ``setToInvoice(false)`` appears nowhere in
``point_of_sale``. So picking a company customer and then clearing it left the
order flagged for invoicing with nobody to invoice, and the server refused it at
posting time with *"you invoiced an invisible man"*. The missing reset is added,
and nothing else.

**The backend Invoice button now refuses early, and says what to do.** On the
order form, that button's only condition is the order's state -- nothing about
the partner -- so pressing it on a walk-in sale invoiced with no check and the
refusal surfaced from four calls down in ``account.move``, phrased as a problem
with an invoice the reader cannot see. The order is now stopped at the button
with a message naming the Customer field and offering the walk-in alternative.
Strictly stricter than core: it refuses only orders core would have refused a
moment later, before any flag is written or document created.

Core's rule that **an invoice requires a customer is left completely intact.**
It is not the defect. A cashier who explicitly asks for an invoice is still
stopped until a customer is named, and no placeholder or walk-in partner is ever
substituted: an invoice either names the real buyer or is not issued.

**A session's Journal Items now include the reversal.** Invoicing a PoS order
makes Odoo post the session closing entry, then reverse that entry's share for
the invoiced order, then issue the invoice. Core's related-moves query omitted
the reversal, so the screen showed revenue credited twice with nothing to
explain it. The books were always correct; the view was not.

Built on Odoo Community (LGPL-3). No Enterprise module is used.
""",
    'depends': ['point_of_sale'],
    'data': [
        'views/pos_order_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'l10n_np_pos/static/src/to_invoice_reset.js',
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
