# Point of Sale (Nepal)

Two corrections to stock Point of Sale, both reported from the live till and both
diagnosed against the database before anything was changed.

## 1. A cash sale can be invoiced without selecting a customer

Stock Odoo already makes the customer optional for a plain cash sale.
`isCustomerRequired` (`point_of_sale/static/src/app/models/pos_order.js:158-169`)
demands one only when the order is **to be invoiced**, when a `split_transactions`
payment method is used, or when a preset needs a name or an address. The reported
case was the first: the order carried `to_invoice = True`, so the till refused to
validate without a customer.

**Business decision:** the customer is optional even when invoicing. The concern
raised at the time — a Nepali VAT tax invoice normally names the buyer, and a PAN
is required above the threshold — was overridden by the owner. Whether an unnamed
buyer satisfies the IRD is **SME sign-off item 6** and remains open.

### Why there is a Walk-in Customer setting

A *genuinely* partnerless invoice does not merely offend an auditor, it breaks.
`_reconcile_invoice_payments` resolves the receivable account through
`_find_accounting_partner(invoice.partner_id).property_account_receivable_id`
(`point_of_sale/models/pos_order.py:1225`). With no partner that is an empty
recordset, so nothing reconciles — **the invoice posts, looks correct, and leaves
an open receivable on every cash sale.** Silently.

So the customer is optional *at the till*, and the configured **Walk-in Customer**
(Point of Sale ▸ Configuration ▸ Settings ▸ Payment) is written onto the order at
invoice time. If none is configured the invoice is **refused**, with a message
naming the setting — failing in front of the person who can fix it beats posting
an invoice that cannot be paid.

### What was deliberately not relaxed

* **Pay-later / Customer Account** methods still require a customer. An
  on-credit sale with no named debtor leaves a receivable nobody can collect.
* **Presets** needing a name (Takeout) or an address (Delivery) still require
  one. A delivery with no address cannot be delivered.

Asserted clause by clause in `static/tests/customer_optional.test.js`, including
the two that must still fire — the risk in deleting one condition from a getter is
not that it stops working, it is that it relaxes something else too.

## 2. A session's Journal Items now include the reversal

Reported as double billing: at `/odoo/pos-sessions/<id>/account.move.line` a single
invoiced 30.00 cash sale appeared twice — the closing entry credited Sales Revenue
30.00 and the invoice credited it again.

**The books were correct.** Invoicing a PoS order after its session closes makes
Odoo post three things:

1. the session closing entry, crediting revenue for every order;
2. a **reversal of that entry's share for the invoiced order**
   (`_create_misc_reversal_move`, fired only when the session is already closed —
   `pos_order.py:1203-1217`);
3. the customer invoice.

Netted across all of them, revenue is credited exactly once. Verified on the
reported data: Sales Revenue −30.00, Cash +30.00, both receivables settled at zero.

**The view was wrong.** Core's `_get_related_account_moves()` returned steps 1 and
3 and omitted step 2 — the one entry that explains why the other two are not a
double count. The list read **60.00 of revenue for a 30.00 sale**. Anyone reading
that screen was right to escalate.

The link already existed and was unused: the reversal carries
`reversed_pos_order_id` (`point_of_sale/models/account_move.py:14`). This module
adds those moves to the set. It is purely additive — it widens a *display* domain
and posts, alters and reconciles nothing, and a test asserts the account balances
are unchanged.

### The `(4)` in the group header is not a duplicate

`show_journal_items` opens that list with `search_default_group_by_move`
(`pos_session.py:1699-1714`), so `POSS/…/0001(4)` is a **group header: one journal
entry containing four lines**. Four debit/credit lines in one entry is ordinary
double-entry bookkeeping, not four bills.

## Licence

LGPL-3, overriding core `point_of_sale` (also LGPL-3), so no licence mixing —
unlike the vendored AGPL-3 OCA modules, where the same approach is refused
(see finding LIC-1).
