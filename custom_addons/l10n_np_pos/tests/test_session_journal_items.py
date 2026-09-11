# -*- coding: utf-8 -*-
r"""A session's Journal Items must show the reversal, and must not move a number.

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_pos --stop-after-init

Reported symptom: the Journal Items of a session containing one invoiced 30.00
cash sale appeared to bill it twice -- the closing entry credited Sales Revenue
30.00 and the invoice credited it again.

Measured on the live data before changing anything: **the books were correct.**
Invoicing a PoS order makes Odoo post three things -- the session closing entry,
a reversal of that entry's share for the invoiced order, and the invoice -- and
netted across all of them revenue is credited exactly once. What was wrong was
the *view*: `_get_related_account_moves()` omitted the reversal, so the list
showed 60.00 of revenue for a 30.00 sale.

A note on an assertion that is NOT made here
--------------------------------------------
The obvious check -- "the Journal Items list balances, debits equal credits" --
is **worthless**, and was written and deleted during this work. Every
`account.move` is internally balanced by construction, so a sum over any set of
whole moves balances whether or not the reversal is included. It would have
passed identically against the bug.

What separates the two states is **revenue specifically**: 30.00 with the
reversal shown, 60.00 without it. That is what these tests assert, and the second
one asserts the broken figure deliberately, so the fix is measured rather than
described.
"""
from odoo import Command
from odoo.tests import TransactionCase, tagged

from .common import create_pos_config


@tagged("-at_install", "post_install")
class TestSessionJournalItems(TransactionCase):

    SALE = 30.0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

    def _closed_session_with_invoiced_cash_order(self):
        """One closed session, one cash order, invoiced -- the reported shape.

        Built rather than searched (TST-3): the reported session exists on this
        database today, but a test depending on it would assert nothing on a
        fresh install and pass vacuously.
        """
        # A DEDICATED config, copied from the live one so it inherits real
        # journals and payment methods.
        #
        # Not the live config, and not shared between tests. `_get_related_account_moves`
        # spans the whole session, so any other order in it contributes revenue
        # too -- and PoS session operations commit, so orders created by one test
        # survive into the next. The first version of this fixture used the live
        # config and both assertions came out a constant 90.00 (three unrelated
        # sales) too high. Isolating the config makes the figures attributable.
        template = create_pos_config(self.env, "PoS JI Test Template")
        # A dedicated cash journal and payment method too, not the live ones.
        #
        # `payment_method_ids` is copy=False, so it does not come across; and a
        # cash method may belong to only one till (`pos.payment.method`'s own
        # ValidationError: "This cash payment method is already used in another
        # Point of Sale"). Both were discovered by trying the cheaper routes.
        company = template.company_id
        journal = self.env["account.journal"].create({
            "name": "PoS JI Test Cash", "code": "JITC", "type": "cash",
            "company_id": company.id,
        })
        cash = self.env["pos.payment.method"].create({
            "name": "PoS JI Test Cash", "journal_id": journal.id,
            "company_id": company.id,
        })
        config = template.copy({
            "name": "PoS JI Test Config",
            "payment_method_ids": [Command.set(cash.ids)],
        })
        self.assertEqual(cash.type, "cash",
                         "the fixture's payment method is not a cash one, so "
                         "this no longer reproduces a cash sale")
        cash = config.payment_method_ids

        partner = self.env["res.partner"].create({"name": "PoS JI Test Customer"})
        product = self.env["product.product"].create({
            "name": "PoS JI Test Product",
            "available_in_pos": True,
            "type": "consu",
            "lst_price": self.SALE,
            "taxes_id": [Command.clear()],
        })

        config.open_ui()
        session = config.current_session_id

        order = self.env["pos.order"].create({
            "session_id": session.id,
            "company_id": config.company_id.id,
            "partner_id": partner.id,
            "to_invoice": False,
            "amount_tax": 0.0,
            "amount_total": self.SALE,
            "amount_paid": self.SALE,
            "amount_return": 0.0,
            "lines": [Command.create({
                "product_id": product.id,
                "qty": 1,
                "price_unit": self.SALE,
                "price_subtotal": self.SALE,
                "price_subtotal_incl": self.SALE,
            })],
        })
        order.payment_ids = [Command.create({
            "payment_method_id": cash[0].id,
            "amount": self.SALE,
            "pos_order_id": order.id,
        })]
        order.action_pos_order_paid()

        # Close FIRST, invoice SECOND. That order is the whole fixture.
        #
        # `_create_misc_reversal_move` runs only when `is_session_closed`
        # (`pos_order.py:1203-1217`), so invoicing before or during close makes
        # Odoo simply exclude the order from the closing entry -- no duplicate,
        # no reversal, and nothing for this module to reveal. The first version
        # of this fixture invoiced during close and all three tests SKIPPED,
        # reporting "0 failed" while asserting nothing: exactly the TST-1/TST-3
        # failure mode. The reported case was an order invoiced after its
        # session closed, and that is what is reproduced here.
        session.action_pos_session_closing_control()
        self.assertEqual(session.state, "closed", "the session did not close")
        order.action_pos_order_invoice()
        return session, order, product

    @staticmethod
    def _net_revenue(moves, product):
        """Credits minus debits on the product's income account."""
        income = product.product_tmpl_id.get_product_accounts()["income"]
        return round(sum(
            line.credit - line.debit
            for line in moves.mapped("line_ids")
            if line.account_id == income
        ), 2)

    def test_revenue_is_shown_once_not_twice(self):
        """The fix, stated as the figure a reader would take off the screen."""
        session, order, product = self._closed_session_with_invoiced_cash_order()

        reversals = self.env["account.move"].search([
            ("reversed_pos_order_id", "=", order.id)])
        self.assertTrue(
            reversals,
            "the fixture produced no closing-entry reversal, so it is not "
            "reproducing the reported case. Invoicing must happen AFTER the "
            "session closes -- see the comment in the fixture. This was a "
            "skipTest and is now a failure, because a test that quietly finds "
            "nothing to assert on is indistinguishable from one that passes")

        shown = session._get_related_account_moves()
        self.assertTrue(
            set(reversals.ids) <= set(shown.ids),
            "the closing-entry reversal is missing from the session's Journal "
            "Items")
        self.assertAlmostEqual(
            self._net_revenue(shown, product), self.SALE, places=2,
            msg="the Journal Items list does not report one sale's worth of "
                "revenue for one sale")

    def test_without_the_reversal_the_same_list_double_counts(self):
        """The negative control: the bug, asserted, so the fix is not merely claimed.

        Excluding the reversal reproduces exactly what core returned, and the
        figure it produces is the one that was reported as double billing. If
        this ever stops being true, the fix above has become unnecessary and
        both tests should go.
        """
        session, order, product = self._closed_session_with_invoiced_cash_order()

        self.assertTrue(
            self.env["account.move"].search_count([
                ("reversed_pos_order_id", "=", order.id)]),
            "no reversal posted, so there is nothing to exclude and this "
            "control asserts nothing")

        core_view = session._get_related_account_moves().filtered(
            lambda move: not move.reversed_pos_order_id)
        self.assertAlmostEqual(
            self._net_revenue(core_view, product), self.SALE * 2, places=2,
            msg="core's move set no longer double-counts revenue, so this "
                "module's override may be redundant")
