/** A cash sale may be invoiced without the cashier selecting a customer.
 *
 * Core's `isCustomerRequired`
 * (`point_of_sale/static/src/app/models/pos_order.js:158-169`) reads:
 *
 *     return invalidPartnerPreset || this.isToInvoice() || Boolean(splitPayment);
 *
 * This removes **only** the `isToInvoice()` clause. The other two are left
 * exactly as they are, and that is a decision rather than an oversight:
 *
 *   - `splitPayment` covers the "Customer Account" method, which is `pay_later`.
 *     An on-credit sale with no named debtor leaves a receivable nobody can
 *     collect, which is not the same problem as a cash sale asking for a name
 *     it does not need.
 *   - `invalidPartnerPreset` covers the Takeout and Delivery presets, which need
 *     a name and an address respectively. A delivery with no address cannot be
 *     delivered.
 *
 * The server keeps the safety net: `pos_order._prepare_invoice_vals` substitutes
 * the configured walk-in customer, or refuses the invoice if none is configured.
 * So this patch relaxes a prompt, it does not decide what gets posted -- the
 * cashier cannot use it to create an invoice the ledger will choke on.
 */
import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    get isCustomerRequired() {
        if (this.partner_id) {
            return false;
        }
        const splitPayment = this.payment_ids.some(
            (payment) => payment.payment_method_id.split_transactions
        );
        const invalidPartnerPreset =
            (this.preset_id?.needsName && !this.floating_order_name) ||
            this.preset_id?.needsPartner;
        // `isToInvoice()` deliberately absent -- see the module docstring.
        return Boolean(invalidPartnerPreset) || Boolean(splitPayment);
    },
});
