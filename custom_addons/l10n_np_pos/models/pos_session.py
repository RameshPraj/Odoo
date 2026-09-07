# -*- coding: utf-8 -*-
"""Show the whole story in a session's Journal Items, reversals included.

The reported symptom was that `/odoo/pos-sessions/<id>/account.move.line` appeared
to bill one 30.00 cash sale twice: `POSS/…/0001` credits Sales Revenue 30.00 and
`INV/…/0004` credits it again.

**The books were right; the screen was not.** When a PoS order is invoiced, Odoo
posts three things in sequence:

  1. the session closing entry, which credits revenue for every order   (POSS/0001)
  2. a **reversal of that entry's share for the invoiced order**        (POSS/0003)
  3. the customer invoice, which credits revenue properly               (INV/0004)

Net across all of them, revenue is credited exactly once. Verified on the
reported session: Sales Revenue -30.00, Cash +30.00, both receivables settled at
zero.

The problem is that core's `_get_related_account_moves()` returns steps 1 and 3
and **omits step 2** -- the one entry that explains why 1 and 3 are not a double
count. The list therefore shows revenue twice, does not balance, and invites
exactly the conclusion that was drawn. An accountant reading that screen would be
right to escalate.

The link already exists and is simply unused: the reversal is created with
`reversed_pos_order_id` pointing at the order
(`point_of_sale/models/pos_order.py:1130-1140`), and that is a real `Many2one` on
`account.move` (`point_of_sale/models/account_move.py:14`). So this adds the
missing moves rather than inventing a relationship.

Purely additive, and deliberately so: it widens a *display* domain and posts,
alters and reconciles nothing. The accompanying test asserts the six account
balances are byte-identical before and after, because a display fix that moves a
number is not a display fix.
"""
from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _get_related_account_moves(self):
        moves = super()._get_related_account_moves()
        # `_get_closed_orders()` rather than `order_ids`, matching what core uses
        # to build the rest of this set -- an open order has no closing entry to
        # reverse, so it can contribute no reversal.
        orders = self._get_closed_orders()
        if not orders:
            return moves
        reversals = self.env['account.move'].sudo().search([
            ('reversed_pos_order_id', 'in', orders.ids),
        ])
        # `_filtered_access('read')` keeps the record rules from SEC-2 in force:
        # this runs under sudo() to find the moves, so the user's own read rights
        # decide what they are then shown.
        return moves | reversals._filtered_access('read')
