# -*- coding: utf-8 -*-
"""Let a cash sale be invoiced without the cashier selecting a customer.

Stock Odoo already makes the customer optional for a plain cash sale.
`isCustomerRequired` (`point_of_sale/static/src/app/models/pos_order.js:158-169`)
demands one only when the order is *to be invoiced*, when a
`split_transactions` payment method is used, or when a preset needs a name or an
address. The reported case was the first of those: the order carried
`to_invoice = True`, so the till asked for a customer before it would validate.

**Decision, taken by the business owner and recorded here rather than argued
again:** the customer is optional even when invoicing. The concern raised at the
time was that a Nepali VAT tax invoice normally names the buyer and requires a
PAN above the threshold; that was overridden. Whether an unnamed buyer satisfies
the IRD remains open under the SME sign-off register, and this docstring exists
so the decision is traceable to a person rather than discovered later as a bug.

Why a fallback partner rather than no partner at all
---------------------------------------------------
A genuinely partnerless invoice does not merely offend an auditor -- it breaks.
Two places in core dereference the partner:

* `_prepare_invoice_vals` does `self.partner_id.address_get(['invoice'])`
  (`pos_order.py:934`);
* `_reconcile_invoice_payments` resolves the receivable account through
  `_find_accounting_partner(invoice.partner_id).property_account_receivable_id`
  (`pos_order.py:1225`). With no partner that is an empty recordset, so
  `receivable_account` is empty, **the reconciliation quietly does nothing**, and
  every cash sale leaves a posted-but-unpaid invoice with an open receivable.

That is a worse defect than the one being fixed, and a silent one. So the
customer is optional *at the till* while the invoice still resolves an accounting
partner: the configured walk-in contact is written onto the order at invoice
time. Writing it to the order rather than only into the invoice vals is
deliberate -- the order should say who it was billed to, and an invoice whose
partner disagrees with its order is a reconciliation puzzle for somebody later.

If no walk-in contact is configured, the invoice is **refused** with a message
naming the setting. Failing at the till, in front of the person who can fix it,
beats posting an invoice that cannot be paid.
"""
from odoo import _, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _prepare_invoice_vals(self):
        """Substitute the walk-in customer before core reads `partner_id`.

        This is the single funnel: `_generate_pos_order_invoice` calls it exactly
        once (`pos_order.py:1197`), and every later partner dereference -- the
        payment term, `address_get`, and the receivable resolution during
        reconciliation -- happens downstream of it.
        """
        missing = self.filtered(lambda order: not order.partner_id)
        if missing:
            # Grouped by config: a multi-shop database can legitimately have a
            # different walk-in contact per till, and one refusal naming the
            # wrong shop would send somebody to the wrong settings page.
            for config, orders in missing.grouped('config_id').items():
                fallback = config.np_pos_default_partner_id
                if not fallback:
                    raise UserError(_(
                        "%(orders)s must be invoiced, but no customer was "
                        "selected and the %(config)s point of sale has no "
                        "Walk-in Customer configured.\n\n"
                        "Set one under Point of Sale > Configuration > "
                        "Settings > Walk-in Customer, or select a customer on "
                        "the order.\n\n"
                        "An invoice with no customer cannot be reconciled "
                        "against its payment, so it would post as unpaid and "
                        "leave the receivable open.",
                        orders=", ".join(orders.mapped('name')),
                        config=config.display_name,
                    ))
                orders.write({'partner_id': fallback.id})
        return super()._prepare_invoice_vals()
