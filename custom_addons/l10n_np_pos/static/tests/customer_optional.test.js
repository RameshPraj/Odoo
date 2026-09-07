/** `isCustomerRequired`: relaxed for invoicing, untouched for everything else.
 *
 * The patch removes exactly one clause from core's getter. That is a small
 * enough change that the risk is not "does it work" but "did it also relax
 * something it should not have" -- so every clause is asserted, including the
 * two that must still fire.
 *
 * The getter is called with a plain object rather than a mounted PoS order: it
 * reads only `partner_id`, `payment_ids`, `preset_id`, `floating_order_name` and
 * `isToInvoice()`, so a fake `this` exercises the real logic with no registry,
 * no RPC and no session. Same reasoning as the matching_cell suite.
 */
import { describe, expect, test } from "@odoo/hoot";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

describe.current.tags("headless");

/** Invoke the patched getter against a fake order. */
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

const splitMethod = { payment_method_id: { split_transactions: true } };
const plainCash = { payment_method_id: { split_transactions: false } };

test("an invoiced order no longer demands a customer", () => {
    // The reported issue. Core returned true here.
    expect(isCustomerRequired({ isToInvoice: () => true })).toBe(false);
});

test("a plain cash order never demanded one", () => {
    expect(isCustomerRequired({ payment_ids: [plainCash] })).toBe(false);
});

test("a pay-later method still demands a customer", () => {
    // Deliberately NOT relaxed: an on-credit sale with no named debtor leaves a
    // receivable nobody can collect.
    expect(isCustomerRequired({ payment_ids: [splitMethod] })).toBe(true);
    // ...and still does when the order is also invoiced, so the removed clause
    // cannot mask this one.
    expect(
        isCustomerRequired({ payment_ids: [splitMethod], isToInvoice: () => true })
    ).toBe(true);
});

test("a preset needing a name still demands one", () => {
    expect(isCustomerRequired({ preset_id: { needsName: true } })).toBe(true);
    // Unless the walk-in name was typed, which is what that preset asks for.
    expect(
        isCustomerRequired({
            preset_id: { needsName: true },
            floating_order_name: "Ramesh",
        })
    ).toBe(false);
});

test("a preset needing an address still demands one", () => {
    // Delivery. An address cannot be inferred from a walk-in customer.
    expect(isCustomerRequired({ preset_id: { needsPartner: true } })).toBe(true);
});

test("a chosen customer short-circuits every rule", () => {
    expect(
        isCustomerRequired({
            partner_id: { id: 7 },
            payment_ids: [splitMethod],
            preset_id: { needsPartner: true },
            isToInvoice: () => true,
        })
    ).toBe(false);
});
