# -*- coding: utf-8 -*-
r"""An invoiced cash sale needs no customer at the till, but the invoice must still pay.

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_pos --stop-after-init

Business decision, recorded rather than re-argued: the customer is optional even
when a cash sale is invoiced. The concern raised at the time -- a Nepali VAT tax
invoice normally names the buyer, and a PAN is required above the threshold -- was
overridden by the owner, and remains open under the SME sign-off register.

The load-bearing test here is **not** that the order posts. It is that the
resulting invoice is actually **paid and reconciled**. Core resolves the
receivable account through
`_find_accounting_partner(invoice.partner_id).property_account_receivable_id`
(`point_of_sale/models/pos_order.py:1225`); with no partner that is an empty
recordset, so `receivable_account` is empty and
`_reconcile_invoice_payments` silently reconciles nothing. The invoice posts,
looks right, and leaves an open receivable on every cash sale. That failure is
silent, which is why it is asserted explicitly.
"""
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCustomerOptional(TransactionCase):

    SALE = 25.0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.config = cls.env["pos.config"].search([], limit=1)
        cls.walk_in = cls.env["res.partner"].create({"name": "Walk-in (test)"})

    def _cash_method(self, split=False):
        methods = self.config.payment_method_ids.filtered(
            lambda m: bool(m.split_transactions) == split
            and (m.type == "cash" or split))
        self.assertTrue(methods, f"no payment method with split={split}")
        return methods[0]

    def _order(self, partner=None, method=None, to_invoice=True):
        self.config.open_ui()
        session = self.config.current_session_id
        product = self.env["product.product"].create({
            "name": "Customer Optional Product",
            "available_in_pos": True, "type": "consu",
            "lst_price": self.SALE, "taxes_id": [Command.clear()],
        })
        order = self.env["pos.order"].create({
            "session_id": session.id,
            "company_id": self.config.company_id.id,
            "partner_id": partner.id if partner else False,
            "to_invoice": to_invoice,
            "amount_tax": 0.0, "amount_total": self.SALE,
            "amount_paid": self.SALE, "amount_return": 0.0,
            "lines": [Command.create({
                "product_id": product.id, "qty": 1,
                "price_unit": self.SALE,
                "price_subtotal": self.SALE,
                "price_subtotal_incl": self.SALE,
            })],
        })
        order.payment_ids = [Command.create({
            "payment_method_id": (method or self._cash_method()).id,
            "amount": self.SALE, "pos_order_id": order.id,
        })]
        return order

    # ---- the decision, and the trap it walks past ------------------------
    def test_an_invoiced_cash_order_with_no_customer_is_paid_and_reconciled(self):
        """The whole point. Posting is not enough -- it has to settle."""
        self.config.np_pos_default_partner_id = self.walk_in
        order = self._order(partner=None)

        order.action_pos_order_paid()
        order._generate_pos_order_invoice()

        invoice = order.account_move
        self.assertTrue(invoice, "no invoice was produced")
        self.assertEqual(
            invoice.partner_id, self.walk_in,
            "the invoice must carry the configured walk-in customer, or its "
            "receivable account cannot be resolved")
        self.assertEqual(
            order.partner_id, self.walk_in,
            "the order should record who it was billed to; an invoice whose "
            "partner disagrees with its order is a puzzle for somebody later")
        self.assertEqual(
            invoice.payment_state, "paid",
            f"the invoice posted but did not settle (state "
            f"{invoice.payment_state!r}). This is the pos_order.py:1225 trap: "
            f"an unresolved receivable account reconciles nothing, silently")

    def test_it_is_refused_when_no_walk_in_customer_is_configured(self):
        """Fail at the till, in front of the person who can fix it."""
        self.config.np_pos_default_partner_id = False
        order = self._order(partner=None)
        order.action_pos_order_paid()

        with self.assertRaises(UserError) as caught:
            order._generate_pos_order_invoice()
        message = str(caught.exception)
        self.assertIn("Walk-in Customer", message,
                      "the refusal must name the setting that fixes it")
        self.assertIn("cannot be reconciled", message,
                      "the refusal should say why, not just that")

    def test_a_chosen_customer_is_never_overridden(self):
        """The control: the fallback must only ever fill a gap."""
        self.config.np_pos_default_partner_id = self.walk_in
        chosen = self.env["res.partner"].create({"name": "A Real Customer"})
        order = self._order(partner=chosen)

        order.action_pos_order_paid()
        order._generate_pos_order_invoice()

        self.assertEqual(order.account_move.partner_id, chosen)
        self.assertEqual(order.partner_id, chosen)

    # ---- what was deliberately left alone --------------------------------
    #
    # `split_transactions` and the preset requirements are enforced in the
    # BROWSER, by `isCustomerRequired`. A Python test cannot assert a till
    # prompt, and the first version of this file tried: it asserted that a
    # fixture's payment method had `split_transactions = True`, which is a
    # property of the fixture rather than of the code, and it SKIPPED on this
    # database because the config carries only Card and Cash.
    #
    # That coverage now lives where it can actually run:
    # static/tests/customer_optional.test.js calls the patched getter directly.
