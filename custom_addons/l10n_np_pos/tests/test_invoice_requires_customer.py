# -*- coding: utf-8 -*-
r"""A walk-in cash sale needs no customer; a requested invoice still does.

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_pos --stop-after-init

Reported symptom, on an ordinary walk-in cash sale:

    Invalid Operation -- The 'Customer' field is required to validate the
    invoice. You probably don't want to explain to your auditor that you
    invoiced an invisible man :)

**Two independent routes reach that message**, and both are covered:

1. *At the till.* ``to_invoice`` is set implicitly when a *company* customer is
   chosen (``pos_order.js:595-597``) and is never reset, so clearing the
   customer afterwards (``pos_store.js:2557`` calls ``setPartner(false)``)
   leaves the order flagged for invoicing with nobody to invoice. Asserted in
   ``static/tests/to_invoice_reset.test.js``.
2. *From the backend order form.* ``/odoo/pos-orders/<id>`` offers an **Invoice**
   button whose only condition is ``state not in ['paid', 'done'] or
   account_move`` (``pos_order_view.xml:10-11``) -- nothing about the partner.
   Pressing it on a walk-in order invoices with no check
   (``pos_order.py:1166-1174``), so the refusal arrives from four calls down.
   Asserted by ``test_3c``/``test_3d``/``test_3e`` below. This route involves no
   JavaScript, which is why the first fix alone did not close the report.

What is asserted **here** is the server half, and the important half is not that
the walk-in sale works -- it is that core's refusal is **still there**. That
validation is not the defect and must never be relaxed, so scenario 3 below
asserts the reported message deliberately, as a control on this module. An
earlier version of this module weakened that rule and substituted a placeholder
partner onto formal invoices; both were reverted, and this file is what would
catch either coming back.

Scenario 5 (a pay-later method with no customer) is enforced in the browser by
``isCustomerRequired``, and is covered in the hoot suite. A Python test cannot
assert a till prompt; the first version of this module tried, and produced a
test that asserted a property of its own fixture and skipped on this database.
"""
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .common import create_pos_config


@tagged("-at_install", "post_install")
class TestInvoiceRequiresCustomer(TransactionCase):

    SALE = 25.0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # A dedicated till, for the reasons learned in
        # test_session_journal_items: `payment_method_ids` is copy=False, and a
        # cash payment method may belong to only one config
        # (`pos.payment.method` raises "This cash payment method is already
        # used in another Point of Sale"). So the journal and the method are
        # built here, not borrowed from the live configuration.
        template = create_pos_config(cls.env, "PoS Invoice Test Template")
        company = template.company_id
        journal = cls.env["account.journal"].create({
            "name": "PoS Invoice Test Cash", "code": "ITCA", "type": "cash",
            "company_id": company.id,
        })
        cls.cash = cls.env["pos.payment.method"].create({
            "name": "PoS Invoice Test Cash", "journal_id": journal.id,
            "company_id": company.id,
        })
        cls.config = template.copy({
            "name": "PoS Invoice Test Config",
            "payment_method_ids": [Command.set(cls.cash.ids)],
        })
        assert cls.cash.type == "cash", "the fixture is no longer a cash sale"
        assert cls.config.invoice_journal_id, (
            "the till has no invoice journal, so scenario 4 could fail to "
            "create an invoice for a reason unrelated to this module")

        cls.customer = cls.env["res.partner"].create({"name": "A Named Buyer"})
        cls.product = cls.env["product.product"].create({
            "name": "PoS Invoice Test Product",
            "available_in_pos": True, "type": "consu",
            "lst_price": cls.SALE, "taxes_id": [Command.clear()],
        })

    def _paid_order(self, partner=None, to_invoice=False):
        """One paid cash order, in whichever of the four states is under test."""
        self.config.open_ui()
        order = self.env["pos.order"].create({
            "session_id": self.config.current_session_id.id,
            "company_id": self.config.company_id.id,
            "partner_id": partner.id if partner else False,
            "to_invoice": to_invoice,
            "amount_tax": 0.0, "amount_total": self.SALE,
            "amount_paid": self.SALE, "amount_return": 0.0,
            "lines": [Command.create({
                "product_id": self.product.id, "qty": 1,
                "price_unit": self.SALE,
                "price_subtotal": self.SALE,
                "price_subtotal_incl": self.SALE,
            })],
        })
        order.payment_ids = [Command.create({
            "payment_method_id": self.cash.id,
            "amount": self.SALE, "pos_order_id": order.id,
        })]
        order.action_pos_order_paid()
        return order

    # ---- 1: no customer, no invoice requested -> succeeds -----------------
    def test_1_walk_in_cash_sale_with_no_customer_succeeds(self):
        """The behaviour the report says must be possible."""
        order = self._paid_order(partner=None, to_invoice=False)

        self.assertEqual(order.state, "paid")
        self.assertFalse(
            order.partner_id,
            "the sale recorded a customer it was never given")
        self.assertFalse(
            order.account_move,
            "a plain cash sale produced a formal invoice; it should leave a "
            "receipt and nothing else")

    # ---- 2: customer, no invoice requested -> succeeds --------------------
    def test_2_cash_sale_with_a_customer_but_no_invoice_succeeds(self):
        """Naming a buyer does not, by itself, mean issuing an invoice."""
        order = self._paid_order(partner=self.customer, to_invoice=False)

        self.assertEqual(order.state, "paid")
        self.assertEqual(order.partner_id, self.customer)
        self.assertFalse(order.account_move, "an unrequested invoice was issued")

    # ---- 3: no customer, invoice requested -> blocked ---------------------
    def test_3_an_invoice_with_no_customer_is_refused(self):
        """The control on this module. Core's rule, asserted by its own words.

        If this test ever fails, something here has re-relaxed the validation
        that the requirement calls out by name, and anonymous customer invoices
        are being posted again.
        """
        order = self._paid_order(partner=None, to_invoice=True)

        with self.assertRaises(UserError) as caught:
            order._generate_pos_order_invoice()

        message = str(caught.exception)
        self.assertIn(
            "field is required", message,
            f"the invoice was refused, but not for the missing customer: "
            f"{message!r}")
        self.assertFalse(
            order.account_move,
            "an invoice was left behind by the refusal, so an anonymous sale "
            "document exists in the books")

    def test_3b_no_placeholder_customer_is_ever_substituted(self):
        """The second half of the control.

        The requirement forbids inventing a customer as much as it forbids
        anonymous invoices. A module that quietly wrote a "Walk-in Customer"
        onto the order would satisfy test 3 by never reaching the refusal at
        all, so the order's own partner is checked after the attempt.
        """
        order = self._paid_order(partner=None, to_invoice=True)
        with self.assertRaises(UserError):
            order._generate_pos_order_invoice()

        self.assertFalse(
            order.partner_id,
            f"the refusal was preceded by a substituted partner "
            f"({order.partner_id.display_name!r}), so formal invoices are "
            f"being issued to a placeholder buyer")

    # ---- 3c/3d: the same refusal via the BACKEND Invoice button -----------
    #
    # A second, independent route to the reported message, with no JavaScript
    # involved: `/odoo/pos-orders/<id>` ▸ Invoice. Reported on order 25, which
    # was `state=done, to_invoice=False, partner_id=NULL`. Core's
    # `action_pos_order_invoice` (`pos_order.py:1166-1174`) writes
    # `to_invoice = True` and invoices with no check on the partner, so the
    # refusal surfaced from `account_move.py:5623` four calls down.
    def test_3c_the_backend_invoice_button_refuses_and_says_why(self):
        """Blocking is correct; the message has to be actionable."""
        order = self._paid_order(partner=None, to_invoice=False)

        with self.assertRaises(UserError) as caught:
            order.action_pos_order_invoice()

        message = str(caught.exception)
        self.assertIn(
            order.display_name, message,
            "the refusal does not say which order it is about")
        self.assertIn(
            "Customer", message,
            f"the refusal does not name the field that fixes it: {message!r}")
        self.assertIn(
            "receipt", message,
            "the refusal does not offer the walk-in alternative, so a cashier "
            "is left thinking the sale itself failed")

    def test_3d_the_refused_button_leaves_the_order_untouched(self):
        """No half-done state, and no reliance on the rollback to undo one.

        Core sets `to_invoice = True` *before* attempting the invoice, so a
        failed attempt is clean only because the transaction unwinds. The guard
        runs ahead of that write, which is why this asserts the flag directly.
        """
        order = self._paid_order(partner=None, to_invoice=False)
        with self.assertRaises(UserError):
            order.action_pos_order_invoice()

        self.assertFalse(order.to_invoice,
                         "the order was left flagged for invoicing")
        self.assertFalse(order.account_move,
                         "a sale document was left behind by the refusal")
        self.assertFalse(order.partner_id,
                         "a placeholder customer was substituted")

    def test_3e_the_guard_does_not_block_an_already_invoiced_order(self):
        """The negative control on the guard's own condition.

        An invoiced order takes core's early-exit branch and never reaches the
        validation, so re-opening its invoice must keep working. A guard that
        only checked `partner_id` would break that for any order invoiced
        before this module was installed.
        """
        order = self._paid_order(partner=self.customer, to_invoice=True)
        order._generate_pos_order_invoice()
        self.assertTrue(order.account_move, "the fixture did not invoice")

        # Blank the partner so the guard's first clause is the only thing that
        # can let this through.
        order.write({'partner_id': False})

        action = order.action_pos_order_invoice()
        self.assertEqual(action.get('res_model'), 'account.move')
        self.assertEqual(action.get('res_id'), order.account_move.id)

    def test_3f_the_invoice_button_is_not_offered_without_a_customer(self):
        """The dead end is removed from the form, not just refused.

        Asserted against the **combined** arch that the web client actually
        receives, not against the module's own file: an `xpath` that stops
        matching after an upstream change would leave the source looking
        correct while the button reverted to core's condition.

        The three clauses are checked individually rather than as one string, so
        the test survives Odoo reformatting the expression.
        """
        from lxml import etree

        arch = self.env["pos.order"].get_view(
            self.env.ref("point_of_sale.view_pos_pos_form").id, "form")["arch"]
        buttons = etree.fromstring(arch).xpath(
            "//button[@name='action_pos_order_invoice']")
        self.assertEqual(
            len(buttons), 1,
            "the Invoice button is no longer in the order form, so this "
            "module's xpath is targeting something that has moved")

        invisible = buttons[0].get("invisible") or ""
        self.assertIn(
            "partner_id", invisible,
            f"the Invoice button is still offered on partnerless orders; the "
            f"view override did not land (condition: {invisible!r})")
        # Core's own two clauses must survive: the override replaces the whole
        # attribute, so dropping one would silently offer Invoice on a draft or
        # an already-invoiced order.
        self.assertIn("state", invisible, "the state condition was lost")
        self.assertIn("account_move", invisible,
                      "the already-invoiced condition was lost")

    # ---- 4: customer, invoice requested -> invoice, paid ------------------
    def test_4_an_invoice_with_a_customer_succeeds_and_settles(self):
        """Posting is not enough -- it has to reconcile.

        `_reconcile_invoice_payments` resolves the receivable through
        `_find_accounting_partner(invoice.partner_id).property_account_receivable_id`
        (`pos_order.py:1225`). A partner that cannot resolve one reconciles
        nothing, silently, leaving a posted-but-unpaid invoice. That failure
        mode is why `payment_state` is asserted rather than just `state`.
        """
        order = self._paid_order(partner=self.customer, to_invoice=True)

        order._generate_pos_order_invoice()

        invoice = order.account_move
        self.assertTrue(invoice, "no invoice was produced")
        self.assertEqual(invoice.partner_id, self.customer)
        self.assertTrue(invoice.is_sale_document())
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(
            invoice.payment_state, "paid",
            f"the invoice posted but did not settle (state "
            f"{invoice.payment_state!r}), leaving the receivable open on a sale "
            f"that was paid in cash at the till")
