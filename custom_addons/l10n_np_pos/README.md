# Point of Sale (Nepal)

Two corrections to stock Point of Sale, both reported from the live till and both
diagnosed against the database before anything was changed.

## 1. A walk-in cash sale is no longer stranded in invoice mode

Reported symptom, on an ordinary walk-in cash sale:

> **Invalid Operation** — The 'Customer' field is required to validate the
> invoice. You probably don't want to explain to your auditor that you invoiced
> an invisible man :)

That text is `account/models/account_move.py:5623`, raised while **posting** a
sale document with no `partner_id`. "Invalid Operation" is only the generic
dialog title Odoo gives any `UserError`
(`web/static/src/core/errors/error_dialogs.js:37`). So the message is *server
side*, and the order had already reached invoice creation — the till was not
merely asking for a name.

**Two independent routes reach that message.** The first fix closed only one of
them, which is why the report came back.

### Route A — at the till: `to_invoice` is set implicitly and never reset

1. `setPartner()` calls `setToInvoice(true)` whenever the chosen partner
   `is_company` (`pos_order.js:595-597`). **Picking a company customer silently
   converts the sale into a formal invoice.** No setting is involved — there is
   no `iface_invoicing` config flag in v19, and `to_invoice` is a plain Boolean
   with no default (`pos_order.py:355`).
2. Nothing ever turns it off. `setToInvoice(false)` appears **nowhere** in
   `point_of_sale/static/src`; core only ever passes `true`.
3. Closing the customer dialog without picking anyone reaches
   `setPartnerToCurrentOrder(payload || false)` (`pos_store.js:2557`), so
   `setPartner(false)` runs — `partner_id` is cleared and `to_invoice` is left
   alone.

After (1) then (3) the order holds `to_invoice = true` with no partner, which is
exactly the state `account_move.py:5623` refuses. The cashier never asked for an
invoice and had no visible way to withdraw the request.

This is a **code defect in core's front-end state management**, not a
configuration problem. Nothing in `pos.config` causes it and no setting fixes it.

**Fix:** `static/src/to_invoice_reset.js` adds the missing reset, and nothing
else — when the partner is cleared, the flag that was set alongside it is
cleared too.

### Route B — the backend Invoice button

Reported against `/odoo/pos-orders/25` (`Ramesh - 000003`:
`state=done, to_invoice=false, partner_id=NULL`). **No JavaScript is involved in
this path at all**, which is why fixing route A did not close the report.

The **Invoice** button on the order form is offered whenever
`state in ('paid', 'done')` and the order is not already invoiced —
`invisible="state not in ['paid', 'done'] or account_move"`
(`point_of_sale/views/pos_order_view.xml:10-11`). **Nothing about the partner.**
`action_pos_order_invoice` (`pos_order.py:1166-1174`) then writes
`to_invoice = True` and invoices with no check, so the refusal arrives from
`account_move.py:5623`, four calls down, phrased as a problem with an invoice the
reader cannot see — while they are looking at a point of sale order, and are not
told that the remedy is to set Customer on the record in front of them.

**Blocking is the correct outcome and is kept.** Pressing that button *is* an
explicit invoice request, so a customer is mandatory. Only the timing and the
wording change: `models/pos_order.py` refuses at the button, before `to_invoice`
is written and before any `account.move` exists, with a message naming the field
and offering the walk-in alternative.

The guard is **strictly stricter** than core — every order it stops is one core
would have stopped a moment later, so it cannot change an outcome core allowed.
Ordering matters beyond phrasing too: core writes `to_invoice = True` *before*
attempting the invoice, so a failed attempt is clean only because the
transaction unwinds. It does today; refusing ahead of that write means
correctness no longer rests on it.

### What was deliberately left alone

Core's rule that **an invoice requires a customer is untouched.** It is not the
defect. All three enforcement points still stand:

* `isCustomerRequired` (`pos_order.js:159-170`), which gates `canBeValidated()`
  (`:719-721`) and disables the Validate button;
* the "Please select the Customer" dialog in
  `order_payment_validation.js:310-323`;
* `account_move.py:5623` on the server, as the last line of defence.

Pressing the **Invoice** toggle does not call `setPartner`, so a cashier who
genuinely wants an invoice is still stopped until a customer is named. Pay-later
/ Customer Account methods and presets needing a name or address still require
one too.

**No placeholder partner is ever substituted.** An invoice either names the real
buyer or is not issued.

### A note on the earlier version of this module

Version `19.0.1.0.0` (commit `40eef74b`) did the opposite of the above: it
patched the `isToInvoice()` clause out of `isCustomerRequired` and substituted a
configured "Walk-in Customer" onto partnerless invoices. Both were **reverted**
in `19.0.2.0.0` as contrary to requirement — anonymous customer invoices and
invented buyers are each ruled out, and the real defect was the sticky flag all
along. The removed pieces were the JS getter patch,
`pos_order._prepare_invoice_vals`, the `pos.config.np_pos_default_partner_id`
field and its settings view.

`test_invoice_requires_customer.py` asserts the reverted behaviour deliberately —
scenario 3 checks the refusal still fires, and `test_3b` checks no partner was
substituted before it — so either coming back is a test failure rather than a
discovery.

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
