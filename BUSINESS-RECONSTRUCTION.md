# What this system does — reconstructed from the codebase

**Method:** installed-module inventory, code tracing, and live database introspection.
**Read-only.** No files or data were modified.

Every statement below is tagged:

| Tag | Meaning |
|---|---|
| ✅ **Confirmed** | Directly evidenced by code or by a database query |
| 🔶 **Inferred** | A reasonable reading of the evidence, but not proven |
| ❓ **Unknown** | Cannot be determined from the codebase; needs a human |

---

## The headline

✅ **Confirmed.** The installed configuration describes a **small-to-mid-size B2B/B2C
selling business with a physical retail counter** — not a manufacturer, not a distributor,
not an online store.

It can: capture leads, quote, sell, reserve and ship stock, invoice, take payment, run a
till, and manage staff.

✅ **Confirmed — and this is the most important finding: it has never been used.**

| Table | Rows |
|---|---:|
| `crm_lead` | **0** |
| `sale_order` | **0** |
| `account_move` | **0** |
| `stock_picking` | **0** |
| `pos_order` | **0** |
| `product_template` | 1 |
| `res_partner` | 40 |
| `hr_employee` | 34 |

Not one business transaction exists. The only populated tables are contacts and employees.
**This is a configured but unexercised system** — everything below describes *capability*,
not observed operation.

✅ **Confirmed.** The company record is untouched Odoo default: `My Company`, country
**US**, currency **USD**, 51 accounts from the generic chart — no country-specific
accounting localization is installed.

🔶 **Inferred contradiction.** A Nepali calendar module (`l10n_np_bs`) and 87 Nepali
translation files were added, implying a **Nepal** operating market — yet the company is
configured as US/USD with a generic chart of accounts. Localization intent and actual
configuration disagree. ❓ **Unknown** which is correct.

---

## 1. Likely users and personas

✅ **Confirmed from `res_groups` membership and installed apps.**

| Persona | Evidence | What they do here |
|---|---|---|
| **Internal employee** (33 users) | `Role / User` group, 33 members | Baseline back-office access |
| **System administrator** (12) | `Administrator` group, 12 members | Configuration, technical settings |
| **HR officer** (2) | `Officer: Manage all employees`, 2 members | Employee records, org chart, skills |
| **Website editor** (2) | `Editor and Designer`, 2 members | Page building via `html_builder` |
| **Portal user** (1) | `Role / Portal`, 1 member | External party — sees own documents only |
| **Public visitor** (1) | `Role / Public`, 1 member | Anonymous website traffic |

🔶 **Inferred from installed apps** — roles the system is *built* for, but which have no
distinguishing group membership yet:

- **Salesperson** — `crm`, `sale`, `sales_team` installed; `crm.lead` and `sale.order` are empty
- **Cashier** — `point_of_sale` + `pos_hr` installed (`pos_hr` exists specifically so
  employees log into the till); zero sessions run
- **Accountant / bookkeeper** — `account` installed; zero journal entries
- **Warehouse operator** — `stock` + `barcodes` + `barcodes_gs1_nomenclature` installed,
  implying scanner-driven picking

❓ **Unknown.** Actual headcount by role, whether the 34 employee records correspond to real
people, and whether any external customer has ever logged into the portal.

---

## 2. Major business capabilities

✅ **Confirmed** — the 10 installed applications (`ir_module_module WHERE application AND
state='installed'`):

| App | Module | Capability |
|---|---|---|
| CRM | `crm` | Lead capture, qualification, pipeline |
| Contacts | `contacts` | Customer/vendor master data |
| Inventory | `stock` | Stock moves, pickings, valuation |
| Invoicing | `account` | Customer invoices, vendor bills, payments |
| Point of Sale | `point_of_sale` | In-person retail till |
| Website | `website` | Public marketing site + forms |
| Employees | `hr` | Staff records, departments, org chart |
| Skills Management | `hr_skills` | Competency and certification tracking |
| Discuss | `mail` | Internal messaging, record chatter |
| Calendar | `calendar` | Meetings and reminders |

Plus non-app capabilities carried by supporting modules:

- **Quotation & sales orders** — `sale`, `sale_crm`, `sale_stock`
- **Electronic invoicing** — `account_edi_ubl_cii`, `sale_edi_ubl` (UBL / Cross-Industry Invoice)
- **Online payment acceptance** — `payment`, `account_payment`, `website_payment`, `pos_online_payment`
- **Outbound SMS** — `sms`, `sale_sms`, `crm_sms`, `stock_sms`, `calendar_sms`, `website_sms`
- **Physical mail** — `snailmail`, `snailmail_account`
- **Analytics dashboards** — `spreadsheet_dashboard*` (sales, POS, stock/accounting)
- **Nepali calendar** — `l10n_np_bs` (local, custom)

### What is deliberately absent

✅ **Confirmed by absence from the installed list** — these shape the business model as much
as what is present:

| Missing module | Consequence |
|---|---|
| `website_sale` | **No eCommerce.** The website is marketing + forms only — it cannot sell |
| `purchase` | **No procurement workflow.** No POs, no vendor RFQs |
| `mrp` | **No manufacturing.** Goods are bought/resold, not made |
| `project`, `hr_timesheet` | No project delivery or time tracking |
| `hr_holidays`, `hr_attendance`, `hr_expense`, `hr_payroll` | HR is records-only — no leave, attendance, expenses or pay |
| `sale_management` | The full Sales app UI is not installed; quotations are reachable from CRM rather than a standalone Sales menu |

🔶 **Inferred.** This is a **sell-side-only** deployment. Money and goods flow *out*
(quote → deliver → invoice → collect); nothing models buying, making, or project delivery.

---

## 3. Primary workflows, traced end to end

Each trace runs **entry point → business logic → persistence / external system**.
All line numbers verified in this tree.

---

### Workflow A — Website enquiry becomes a lead

✅ **Confirmed** (code path exists and is wired). 🔶 **Inferred** that it is used — `crm_lead`
is empty.

```
Anonymous visitor submits a form on the public site
        │
        ▼
website/controllers/form.py:31
   @http.route('/website/form/<string:model_name>', type='http', auth="public",
               methods=['POST'], website=True, csrf=False, captcha='website_form')
        │  gated by Google reCAPTCHA (module google_recaptcha installed)
        ▼
website_crm/controllers/website_form.py:24  _handle_website_form()
   :25  checks ir.model.website_form_access — only whitelisted models accept posts
        │
        ▼
website_crm/models/crm_lead.py:47  website_form_input_filter()
   normalises submitted values; phone formatted via phone_validation
        │
        ▼
PERSISTENCE:  crm.lead  row created
        │
        ▼
ENRICHMENT (async):  cron "CRM: enrich leads (IAP)" every 24h
   → outbound call to Odoo IAP (modules crm_iap_enrich, crm_iap_mine)
```

**Security note** ✅: `csrf=False` on a public POST route is intentional — the captcha
replaces CSRF here. Anything added to that whitelist becomes publicly writable.

---

### Workflow B — Inbound email becomes a business record

✅ **Confirmed, and configured with live routing.** Three aliases exist in `mail_alias`:

| Alias | Routes to | Who may post |
|---|---|---|
| `info@` | `crm.lead` | everyone |
| `sales@` | `account.move` | everyone |
| `purchases@` | `account.move` | everyone |

```
Incoming email fetched from a mail server
        │
        ▼
mail/models/mail_thread.py:1121  message_route()
   resolves recipient alias → target model + thread
        │
        ▼
mail/models/mail_thread.py:1437  message_process()
   parses MIME, extracts body + attachments
        │
        ▼
mail/models/mail_thread.py:1514  message_new()
   creates the target record from the message
        │
        ▼
PERSISTENCE:  crm.lead  or  account.move  +  mail.message  +  ir.attachment (filestore)
```

🔶 **Inferred and notable:** `sales@` and `purchases@` both create **`account.move`** — i.e.
emailing an invoice or bill into the system creates an accounting document directly. Given
`purchase` is not installed, `purchases@` is how **vendor bills** are intended to arrive.

❓ **Unknown.** Whether any incoming mail server is actually configured and polling — I did
not read `fetchmail.server`. Without one, these aliases are inert.

---

### Workflow C — Order to delivery to invoice (the core money path)

✅ **Confirmed** code path; 🔶 **inferred** business use (`sale_order` is empty).

```
Salesperson confirms a quotation  (or portal customer accepts online)
        │
        ▼
sale/models/sale_order.py:1167  action_confirm()
   :1232  _action_confirm()          → state: draft → sale
        │
        ▼  bridge module sale_stock takes over
sale_stock/models/sale_order.py:213  _action_confirm()
sale_stock/models/sale_order_line.py:381  _action_launch_stock_rule()
        │  runs procurement against stock.rule
        ▼
PERSISTENCE:  stock.picking + stock.move  (a delivery order)
        │
        ▼  warehouse validates the delivery
stock/models/stock_move.py:2244  _action_done()
        │
        ▼  accounting bridge stock_account extends the same method
stock_account/models/stock_move.py:177  _action_done()
        │
        ▼
PERSISTENCE:  account.move  (inventory valuation journal entry)
        │
        ▼  back on the order
sale/models/sale_order.py:1551  _create_invoices()
        │
        ▼
PERSISTENCE:  account.move (customer invoice, draft)
        │
        ▼
account/models/account_move.py:5557  _post()
   validates, assigns a gapless number via sequence.mixin,
   enforces debit = credit, optionally hash-chains the entry
        │
        ▼
PERSISTENCE:  account.move (posted) + account.move.line (double-entry)
```

**Design point worth knowing** ✅: `sale_stock` and `stock_account` are *bridge* modules —
neither `sale` nor `stock` nor `account` depends on the others. Each bridge extends
`_action_confirm` / `_action_done` on the module it joins. This is why the chain above
crosses four modules without any of them importing another.

---

### Workflow D — Retail sale at the till

✅ **Confirmed** code path; 🔶 **inferred** use (`pos_order` is empty; no session ever run).

```
Cashier opens a session and sells at the POS screen (offline-capable client)
        │
        ▼
PERSISTENCE (local first):  pos.order accumulates during the session
        │
        ▼  end of shift
point_of_sale/models/pos_session.py:384  action_pos_session_closing_control()
   :420  _validate_session()        → cash counted, differences resolved
        │
        ▼
point_of_sale/models/pos_session.py:868  _create_account_move()
        │
        ▼
PERSISTENCE:  account.move  (one summarised journal entry per session)
              + stock moves for goods sold
```

✅ **Confirmed:** `pos_hr` is installed — cashiers identify as **`hr.employee`** records, not
as Odoo users. This links the till to the HR data that *is* populated (34 employees).

✅ **Confirmed:** `pos_online_payment` is installed, so the till can request payment through
an online provider — but see Workflow E: no provider is enabled.

---

### Workflow E — Getting paid

✅ **Confirmed — and currently non-functional.**

```
Customer clicks pay on a portal invoice or POS request
        │
        ▼
payment/models/payment_transaction.py:1112  _post_process()
        │
        ▼
account_payment/models/payment_transaction.py:98   _post_process()
account_payment/models/payment_transaction.py:133  _create_payment()
        │
        ▼
PERSISTENCE:  account.payment → account.move → reconciled against the invoice
```

✅ **Confirmed blocker:** `payment_provider` holds **24 rows, every one `state = disabled`
with `code = 'none'`**. No payment method is enabled. **Online collection cannot occur
today** — the code path exists but has no provider behind it.

---

### Workflow F — Delivering the invoice to the customer

✅ **Confirmed** code path.

```
account/models/account_move_send.py:816  _generate_and_send_invoices()
        │  also invoked by cron "Send invoices automatically" (daily)
        ├─► :657 _send_mails() / :555 _send_mail()   → email + PDF attachment
        ├─► snailmail_account                        → physical letter via Odoo IAP
        └─► account_edi_ubl_cii / sale_edi_ubl       → structured UBL / CII e-invoice
```

🔶 **Inferred:** the presence of `account_edi_ubl_cii`, `sale_edi_ubl` and `account_add_gln`
(Global Location Number) points at **B2B trading partners that require structured
e-invoicing** — typically an EU/Peppol-style regime or a large-buyer mandate.

---

### Workflow G — Employee lifecycle

✅ **Confirmed, and the only workflow with real data** (34 employees, populated org chart).

```
HR officer creates an employee  →  hr.employee
        ├─ department + manager chain     (hr, hr_org_chart)
        ├─ skills and certifications      (hr_skills)
        ├─ home/office working schedule   (hr_homeworking, hr_homeworking_calendar)
        └─ optional POS badge identity    (pos_hr)
        │
        ▼  monitored by three daily crons
   "HR Employee: Notify Expiring Contract or Work Permit"
   "Skills: Add an activity to employees with missing or expiring certifications"
   "HR Employee: Update Current Version"
```

✅ **Confirmed structural detail:** in Odoo 19 `hr.employee` uses
`_inherits = {'hr.version': 'version_id'}` — job title, department and contract data live on
a versioned `hr.version` record, giving employment **history**, not just current state.

---

## 4. User entry points

✅ **Confirmed** from route definitions and installed modules.

| Entry point | Route / mechanism | Audience |
|---|---|---|
| Back-office web client | `/odoo` → `web` module | Internal staff |
| Login | `/web/login` (+ TOTP, passkeys) | All users |
| Self-signup | `auth_signup` installed | New portal users |
| Customer portal | `portal` module | Customers viewing own documents |
| Public website | `website` + `http_routing` | Anonymous visitors |
| Website forms | `website/controllers/form.py:31` | Anonymous → creates records |
| Point of Sale client | `point_of_sale` offline OWL app | Cashiers |
| Inbound email | 3 aliases (`info@`, `sales@`, `purchases@`) | Anyone who can email |
| XML-RPC / JSON-RPC | `/xmlrpc/2`, `/jsonrpc` | External systems |
| JSON-2 REST | `/json/2/<model>/<method>`, bearer auth | External systems |
| Barcode scanner | `barcodes`, `barcodes_gs1_nomenclature` | Warehouse / POS |

---

## 5. Scheduled and background processes

✅ **Confirmed — 24 active `ir.cron` records.** Grouped by business purpose:

**Revenue and accounting**
- `Account: Post draft entries with auto_post enabled…` — daily, posts scheduled entries
- `Send invoices automatically` — daily, drives Workflow F
- `Stock Account: Inventory Valuation Closing` — daily

**Supply**
- `Procurement: run scheduler` (`stock.rule`) — daily; the replenishment engine

**Sales and marketing**
- `CRM: enrich leads (IAP)` — every 24h, **outbound to Odoo SA**
- `Digest Emails` — daily KPI summary to subscribers
- `Website Visitor: clean inactive visitors` — daily

**Communications (queue drains)**
- `Mail: Email Queue Manager` — **hourly**
- `SMS: SMS Queue Manager` — 24h
- `Snailmail: process letters queue` — 24h
- `Mail: send web push notification`, `Post scheduled messages`, `Notify scheduled messages`
- `Notification: Delete Notifications older than 6 Months` — monthly retention

**HR**
- `HR Employee: Notify Expiring Contract or Work Permit` — daily
- `Skills: Add an activity to employees with missing/expiring certifications` — daily
- `HR Employee: Update Current Version` — daily

**Platform hygiene**
- `Base: Auto-vacuum internal data`, `Base: Portal Users Deletion`,
  `Users: Notify About Unregistered Users`, `Calendar: Event Reminder`,
  `Disable unused snippets assets`, `Publisher: Update Notification`

⚠️ ✅ **Confirmed operational risk:** `odoo.conf` sets `max_cron_threads = 2`. All 24 jobs
share two worker threads.

---

## 6. Inbound integrations

✅ **Confirmed capability.**

| Channel | Mechanism | Status |
|---|---|---|
| Email → records | `mail_alias` × 3 → `crm.lead`, `account.move` | Aliases configured; ❓ mail server unknown |
| Web forms → records | `website/controllers/form.py:31` | Route active, captcha-gated |
| XML-RPC / JSON-RPC | `addons/rpc/controllers/` | Available |
| JSON-2 REST (bearer) | `rpc/controllers/json2.py:38-55` | Available |
| Incoming payment webhooks | `payment` provider controllers | **Inert — no provider enabled** |
| Barcode input | `barcodes`, GS1 nomenclature | Available |
| IoT devices | `iot_base` installed | ❓ no device configured |

---

## 7. Outbound integrations

✅ **Confirmed capability**, ❓ **unknown whether credentialed**.

| Target | Module | Purpose |
|---|---|---|
| SMTP | `base` `ir_mail_server` | All outbound email |
| Google Gmail | `google_gmail` | OAuth mail sending |
| Microsoft Outlook | `microsoft_outlook` | OAuth mail sending |
| Google Maps / Places | `google_address_autocomplete` | Address completion |
| Google reCAPTCHA | `google_recaptcha` | Public form protection |
| **Odoo IAP** | `iap`, `iap_crm`, `iap_mail`, `crm_iap_enrich`, `crm_iap_mine`, `partner_autocomplete` | **Metered, paid calls to Odoo SA** |
| SMS gateway | `sms` (+5 bridges) | Transactional SMS, via IAP |
| Physical mail | `snailmail`, `snailmail_account` | Printed letters, via IAP |
| Unsplash | `web_unsplash` | Stock imagery for the website |
| Payment providers | `payment` + 23 provider modules | **All disabled** |
| E-invoicing networks | `account_edi_ubl_cii`, `sale_edi_ubl` | Structured invoice exchange |
| Publisher warranty | `publisher_warranty.contract` cron | Weekly call to Odoo SA |

⚠️ 🔶 **Inferred risk:** at least seven distinct paths call **Odoo SA** infrastructure
(IAP-family + publisher warranty). Two run automatically on a cron. In an air-gapped or
egress-restricted deployment these will fail repeatedly and noisily.

---

## 8. Data generated and consumed

✅ **Confirmed** — models the code writes, and their current row counts.

**Master data (consumed by nearly every workflow)**

| Entity | Model | Rows now |
|---|---|---:|
| Contacts | `res.partner` | 40 |
| Products | `product.template` | **1** |
| Employees | `hr.employee` (+ `hr.version`) | 34 |
| Chart of accounts | `account.account` | 51 (generic) |
| Units of measure | `uom.uom` (`uom` module) | — |

**Transactional data (generated by operation)**

| Entity | Model | Rows now |
|---|---|---:|
| Leads | `crm.lead` | 0 |
| Quotations / orders | `sale.order` | 0 |
| Deliveries | `stock.picking` / `stock.move` | 0 |
| Invoices, bills, journal entries | `account.move` / `account.move.line` | 0 |
| Payments | `account.payment` | 0 |
| POS sessions and orders | `pos.session` / `pos.order` | 0 |

**Cross-cutting data generated by the framework**

- `mail.message` + `mail.notification` — audit trail on every chattered record
- `ir.attachment` — documents and images; **binary content lives on disk** in
  `.odoo_data/filestore`, not in the database
- `mail.activity` — the to-do system HR crons write into
- `website.visitor` — anonymous traffic tracking
- `ir.logging`, `ir.profile` — technical telemetry

❓ **Unknown.** Whether the 40 contacts and 34 employees are real people or seeded test data,
and therefore whether this database holds personal data subject to privacy obligations. The
`privacy_lookup` module is installed, which suggests someone anticipated GDPR-style
subject-access requests.

---

## 9. Summary — confirmed / inferred / unknown

### ✅ Confirmed from code and data

1. Ten business apps installed: CRM, Sales(support), Inventory, Invoicing, POS, Website, Employees, Skills, Discuss, Calendar
2. **Zero transactions** — every operational table is empty
3. Only real data is 40 contacts, 34 employees, 1 product
4. Company is Odoo default: My Company / US / USD / generic chart of accounts
5. Three inbound email aliases are live: `info@`→lead, `sales@`+`purchases@`→accounting
6. All 24 payment providers are **disabled** — online collection is impossible today
7. 24 cron jobs active, sharing 2 worker threads
8. No eCommerce, no purchasing, no manufacturing, no project, no payroll/leave/expenses
9. Order-to-cash chain is wired across four modules via bridges (`sale_stock`, `stock_account`)
10. POS cashiers authenticate as employees (`pos_hr`), tying the till to HR data

### 🔶 Inferred

1. A **sell-side SMB with a retail counter** — quote/deliver/invoice plus a till
2. Goods are **bought in and resold** (no manufacturing, no BoM)
3. B2B customers requiring **structured e-invoicing** (UBL/CII + GLN)
4. **Nepal** market intent (custom BS calendar + Nepali translations) contradicting US/USD configuration
5. Warehouse work is **barcode-driven** (GS1 nomenclature installed)
6. `purchases@` is the intended vendor-bill intake route, since `purchase` is absent
7. The system is at **pre-launch / evaluation stage** — configured, populated with staff, never transacted

### ❓ Unknown — cannot be determined from the codebase

1. Whether this is a sandbox, a build-in-progress, or a stalled go-live
2. Whether the 34 employees and 40 contacts are real people (privacy exposure)
3. Whether an inbound mail server is configured and polling — aliases are inert without one
4. Whether any outbound integration holds live credentials
5. Which market is authoritative — the US company config or the Nepali localization work
6. Why `purchases@` routes to `account.move` with no purchasing module — deliberate or leftover
7. Whether the single product is a placeholder or the actual catalogue
8. Who the intended end users are; the group membership reflects setup activity, not an operating org

---

*Reconstructed read-only from the installed module set, route and model definitions, and
live queries against `odoo19`. Row counts are point-in-time. No project code, configuration,
or data was modified.*
