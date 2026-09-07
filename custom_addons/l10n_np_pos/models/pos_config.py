# -*- coding: utf-8 -*-
"""The walk-in customer a cash invoice falls back to.

Configuration rather than a shipped record with an xmlid, for the reason stated
throughout this suite: a value that differs per company and per business is a
record an authorised user edits, not a constant in source. A shop that wants
"Cash Customer", one that wants "Walk-in", and one that wants its own trading
name are all correct, and none of them should need a developer.

There is deliberately **no default**. If it is unset, an invoiced order with no
customer is refused with a message naming this field -- see
`pos_order._prepare_invoice_vals`. Silently inventing a partner would be worse:
the invoice would post, look fine, and leave an unreconciled receivable that
nobody is looking for.
"""
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    np_pos_default_partner_id = fields.Many2one(
        'res.partner',
        string="Walk-in Customer",
        check_company=True,
        help="Used as the invoice customer when a cashier issues an invoice "
             "without selecting one. Leave empty to refuse such invoices "
             "instead. It is only ever substituted on invoices -- a plain cash "
             "receipt records no customer at all.",
    )
