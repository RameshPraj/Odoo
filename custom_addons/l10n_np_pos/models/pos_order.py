# -*- coding: utf-8 -*-
"""Refuse the backend Invoice button early, and say what to do about it.

This is the **second** route to the reported message, and it involves no
JavaScript at all. Reported against `/odoo/pos-orders/25` -- the backend order
form, not the till.

`action_pos_order_invoice` (`pos_order.py:1166-1174`) writes `to_invoice = True`
and calls `_generate_pos_order_invoice()` with no check on the partner. On a
walk-in order the refusal therefore arrives from
`account_move.py:5619-5624`, four calls deep, phrased as

    The 'Customer' field is required to validate the invoice.
    You probably don't want to explain to your auditor that you invoiced an
    invisible man :)

and titled "Invalid Operation", which is only the generic label Odoo gives any
`UserError` (`web/static/src/core/errors/error_dialogs.js:37`). The reader is
looking at a *point of sale order*, is told about an *invoice* they cannot see,
and is not told that the fix is to set Customer on the record in front of them.

The button offers the dead end unconditionally: its only condition is
`state not in ['paid', 'done'] or account_move`
(`point_of_sale/views/pos_order_view.xml:10-11`), which says nothing about the
partner.

Blocking is the correct outcome and is deliberately kept
------------------------------------------------------
Pressing that button **is** an explicit request for an invoice, so a customer is
mandatory and the order must be refused. Core's validation is not the defect and
nothing here relaxes it: no partner is invented, no placeholder is substituted,
and an invoice is still never posted without a named buyer.

What changes is only *when* and *how* the refusal happens. The guard runs before
`to_invoice` is written and before any `account.move` exists, so it cannot alter
an outcome core would have allowed -- every order it stops is one core would
have stopped a moment later. It is strictly stricter, and only the message and
its timing differ.

Ordering also matters for a reason beyond phrasing. Core writes `to_invoice =
True` *before* attempting the invoice, so the failed attempt depends on the
transaction rolling back to leave the flag clean. It does today. Refusing before
the write means correctness does not rest on that.
"""
from odoo import _, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def action_pos_order_invoice(self):
        """Stop a partnerless order at the button, naming the field to fill.

        Guarded on `not account_move` to match the button's own condition: an
        order that is already invoiced takes core's early-exit branch and never
        reaches the validation, so refusing it here would break re-opening an
        existing invoice.
        """
        for order in self:
            if order.account_move or order.partner_id:
                continue
            raise UserError(_(
                "%(order)s has no customer, so it cannot be invoiced.\n\n"
                "Set Customer on this order and press Invoice again -- a tax "
                "invoice is a legal document naming the buyer, and it needs a "
                "partner to carry the receivable it settles.\n\n"
                "If this was an ordinary walk-in sale, no invoice is needed. "
                "The sale is already recorded and paid: its revenue, tax and "
                "stock are posted through the session's closing entry, and the "
                "customer has the point of sale receipt.",
                order=order.display_name,
            ))
        return super().action_pos_order_invoice()
