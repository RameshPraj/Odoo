/** Clearing the customer must also clear the "to invoice" flag.
 *
 * The reported symptom was a backend refusal on an ordinary walk-in cash sale:
 *
 *     Invalid Operation -- The 'Customer' field is required to validate the
 *     invoice. You probably don't want to explain to your auditor that you
 *     invoiced an invisible man :)
 *
 * That text is `account/models/account_move.py:5623`, raised while *posting* a
 * sale document with no `partner_id`. "Invalid Operation" is merely the generic
 * dialog title Odoo gives any `UserError`
 * (`web/static/src/core/errors/error_dialogs.js:37`), so the message is server
 * side and the order had already reached invoice creation.
 *
 * How an order gets there, in core, with nobody asking for an invoice
 * -------------------------------------------------------------------
 * `to_invoice` is set implicitly and never reset:
 *
 *   1. `setPartner()` calls `setToInvoice(true)` whenever the chosen partner
 *      `is_company` (`pos_order.js:595-597`). Picking a company customer
 *      silently converts the sale into a formal invoice. No setting is involved
 *      -- there is no `iface_invoicing` config flag in v19.
 *   2. Nothing ever turns it off. `setToInvoice(false)` does not appear anywhere
 *      in `point_of_sale/static/src`; core only ever passes `true`.
 *   3. Closing the customer dialog without picking anyone reaches
 *      `setPartnerToCurrentOrder(payload || false)` (`pos_store.js:2557`), so
 *      `setPartner(false)` runs: `partner_id` is cleared and `to_invoice` is
 *      left alone.
 *
 * After (1) then (3) the order holds `to_invoice = true` with no partner, which
 * is exactly the state `account_move.py:5623` refuses. The cashier never asked
 * for an invoice and has no visible way to withdraw the request.
 *
 * What this does, and what it deliberately does not
 * -------------------------------------------------
 * Only the missing reset is added: when the partner is cleared, the flag that
 * was set alongside it is cleared too. That is the smallest change that removes
 * the impossible state.
 *
 * Core's "a customer is required to invoice" rule is **left completely intact**.
 * It is not the defect. An explicit request for an invoice still demands a
 * customer, in all three places that enforce it:
 *
 *   - `isCustomerRequired` (`pos_order.js:159-170`), which gates
 *     `canBeValidated()` (`:719-721`) and disables the Validate button;
 *   - the "Please select the Customer" dialog in
 *     `order_payment_validation.js:310-323`;
 *   - `account_move.py:5623` on the server, as the last line of defence.
 *
 * Pressing the Invoice toggle does not call `setPartner`, so a cashier who
 * genuinely wants an invoice is still stopped until they name a customer. No
 * substitute or placeholder partner is ever invented: an invoice either names
 * the real buyer or is not issued.
 */
import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    setPartner(partner) {
        super.setPartner(...arguments);
        // Guarded rather than unconditional: `setToInvoice` writes through
        // `assertEditable()` and marks the order dirty, and clearing a flag that
        // is already clear would sync every customer change for no reason.
        if (!partner && this.isToInvoice()) {
            this.setToInvoice(false);
        }
    },
});
