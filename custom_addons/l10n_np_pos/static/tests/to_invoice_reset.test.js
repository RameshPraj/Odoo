/** The sticky `to_invoice` flag, and the rule that must survive the fix.
 *
 * Two things are asserted here, and the second matters as much as the first:
 *
 *   1. Clearing the customer clears `to_invoice` -- the fix.
 *   2. An explicit invoice request STILL demands a customer -- core's rule,
 *      which this module must not have weakened. An earlier version of this
 *      module patched that rule away; these tests are what would catch its
 *      return.
 *
 * `setPartner` is called against a plain object rather than a mounted PoS order.
 * It touches only `partner_id`, `assertEditable()`,
 * `updatePricelistAndFiscalPosition()` and the two invoice accessors, so a fake
 * `this` exercises the real logic with no registry, no RPC and no session.
 * `super` inside a patched method resolves through the method's home object, not
 * through `this`, so the core implementation really does run.
 */
import { describe, expect, test } from "@odoo/hoot";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

describe.current.tags("headless");

/** A fake order that records what was written to it. */
function makeOrder(overrides = {}) {
    return {
        partner_id: null,
        to_invoice: false,
        setToInvoiceCalls: 0,
        assertEditable() {},
        updatePricelistAndFiscalPosition() {},
        setToInvoice(value) {
            this.setToInvoiceCalls++;
            this.to_invoice = value;
        },
        isToInvoice() {
            return this.to_invoice;
        },
        ...overrides,
    };
}

function setPartner(order, partner) {
    PosOrder.prototype.setPartner.call(order, partner);
    return order;
}

/** Core's getter, invoked directly. */
function isCustomerRequired(order) {
    const descriptor = Object.getOwnPropertyDescriptor(
        PosOrder.prototype,
        "isCustomerRequired"
    );
    return descriptor.get.call({
        partner_id: null,
        payment_ids: [],
        preset_id: null,
        floating_order_name: null,
        isToInvoice: () => false,
        ...order,
    });
}

const company = { id: 1, name: "A Company Ltd", is_company: true };
const individual = { id: 2, name: "A Person", is_company: false };

// ---- 1. the fix ---------------------------------------------------------

test("clearing the customer clears the invoice flag", () => {
    // The reported bug, in two steps. Core leaves `to_invoice` true here, which
    // is the state `account_move.py:5623` refuses on the server.
    const order = setPartner(makeOrder(), company);
    expect(order.to_invoice).toBe(true, {
        message: "core no longer flags a company sale to-invoice; if that is " +
            "deliberate upstream, this module's reset may be redundant",
    });

    setPartner(order, false);
    expect(order.partner_id).toBe(false);
    expect(order.to_invoice).toBe(false, {
        message: "the invoice flag survived the customer being cleared, so a " +
            "walk-in cash sale is still stranded in invoice mode",
    });
});

test("clearing an already-unflagged order writes nothing", () => {
    // Not cosmetic: `setToInvoice` goes through `assertEditable()` and dirties
    // the order, which would sync on every customer change.
    const order = setPartner(makeOrder(), individual);
    expect(order.to_invoice).toBe(false);
    const before = order.setToInvoiceCalls;

    setPartner(order, false);
    expect(order.setToInvoiceCalls).toBe(before);
});

test("choosing a customer is unaffected in both directions", () => {
    // The company rule still fires...
    expect(setPartner(makeOrder(), company).to_invoice).toBe(true);
    // ...an individual still does not trigger it...
    expect(setPartner(makeOrder(), individual).to_invoice).toBe(false);
    // ...and an explicit request is not undone by then naming someone.
    const requested = makeOrder({ to_invoice: true });
    setPartner(requested, individual);
    expect(requested.to_invoice).toBe(true, {
        message: "naming a customer withdrew an invoice the cashier asked for",
    });
});

// ---- 2. the rule that must not have been weakened -----------------------

test("an explicit invoice request still demands a customer", () => {
    // This is the control on this module itself. If it ever returns false, the
    // till will let a partnerless invoice through to the server, which is the
    // behaviour that was reverted.
    expect(isCustomerRequired({ isToInvoice: () => true })).toBe(true);
});

test("a pay-later method still demands a customer", () => {
    const payLater = { payment_method_id: { split_transactions: true } };
    expect(isCustomerRequired({ payment_ids: [payLater] })).toBe(true);
});

test("presets needing a name or an address still demand one", () => {
    expect(isCustomerRequired({ preset_id: { needsName: true } })).toBe(true);
    expect(isCustomerRequired({ preset_id: { needsPartner: true } })).toBe(true);
    expect(
        isCustomerRequired({
            preset_id: { needsName: true },
            floating_order_name: "Ramesh",
        })
    ).toBe(false);
});

test("a plain cash sale with no customer is allowed through", () => {
    // Requirement 1: this must be true both before and after the fix, and is
    // the reason the reset is targeted at the flag rather than at the rule.
    const plainCash = { payment_method_id: { split_transactions: false } };
    expect(isCustomerRequired({ payment_ids: [plainCash] })).toBe(false);
});
