# Runtime architecture — entry points and call flows

**Method:** static trace of the process bootstrap, dispatch chain and worker model.
**Read-only.** No code was modified. All line numbers verified in this tree.

Tags used throughout: ✅ **Confirmed** (read from code) · 🔶 **Inferred** · ❓ **Unknown**

---

## 0. The shape of it

✅ **Confirmed.** There is exactly **one process entry point**. Everything else — HTTP, cron,
websockets, CLI tooling — is a *mode* selected after that entry, inside the same interpreter.

```
odoo/__main__.py  ──►  odoo/cli/command.py:109  main()
                            │
                            ├─ resolves argv[0] to a Command subclass  (:92 find_command)
                            │
                            ├─ "server" (default) ──► odoo/service/server.py:1616  start()
                            │                              │
                            │                              ├─ GeventServer   (:1625, if --gevent-port worker)
                            │                              ├─ PreforkServer  (:1630, if config['workers'])
                            │                              └─ ThreadedServer (else)  ◄── THIS INSTANCE
                            │
                            └─ shell / db / scaffold / populate / cloc / neutralize / upgrade_code / …
                                   (14 built-in commands, no HTTP listener)
```

✅ **Confirmed for this instance:** `odoo.conf` sets `workers = 0`, so
`odoo/service/server.py` selects **`ThreadedServer`** (`:451`). Prefork is unavailable
anyway — `requirements.txt` excludes gevent/greenlet on `sys_platform == 'win32'`.

✅ **Confirmed: there is no MCP server or client** anywhere in this codebase. A
case-insensitive search for `modelcontextprotocol`, `mcp_server`, `mcp_client` and `"mcp"`
across all `.py`, `.js`, `.json`, `.txt` and `.md` files (excluding `venv/`) returns **zero
matches**.

---

## 1. Thread and worker inventory (this instance)

✅ **Confirmed** from `ThreadedServer.start()` (`odoo/service/server.py:637`).

| Thread | Spawned by | Count | Purpose |
|---|---|---:|---|
| Main / WSGI | `http_spawn()` `:629` | 1 listener, N request threads | Serves every HTTP request |
| Cron workers | `cron_spawn()` `:614` → `cron_thread()` `:536` | **2** | Executes `ir.cron` jobs |
| Signal/limit watchdog | `ThreadedServer.run()` `:700` | 1 | Memory/time limits, reload |

✅ `max_cron_threads = 2` in `odoo.conf` — **24 active cron jobs share 2 threads.**

✅ **Confirmed cross-process coordination:** because multiple workers (or a second process
such as a CLI run) can mutate the schema, each request re-checks a database-held sequence
before using its cached registry — `odoo/orm/registry.py:1084` `get_sequences()`, invoked via
`check_signaling()`. This is how a `-u module` run in one process invalidates the registry
in another.

---

## 2. Entry point catalogue

| # | Entry point | Trigger | Implementation |
|---|---|---|---|
| 1 | Process `main()` | `python -m odoo` / `odoo` script | `odoo/__main__.py`; `setup/odoo`; `cli/command.py:109` |
| 2 | Server startup | default CLI command | `service/server.py:1616 start()` |
| 3 | WSGI application | every HTTP request | `odoo/http.py:2812 Application.__call__` |
| 4 | Controller routes | URL match | `@http.route`, `odoo/http.py:755` |
| 5 | RPC services | `/xmlrpc/2`, `/jsonrpc` | `odoo/http.py:428 dispatch_rpc`; `addons/rpc/controllers/` |
| 6 | JSON-2 REST | `/json/2/<model>/<method>` | `addons/rpc/controllers/json2.py:38-55` |
| 7 | Scheduled jobs | cron thread wakeup / PG `NOTIFY` | `ir_cron.py:187 _process_jobs` |
| 8 | WebSocket | HTTP `Upgrade: websocket` | `bus/websocket.py:976 WebsocketConnectionHandler` |
| 9 | Inbound email | mail fetch → alias routing | `mail_thread.py:1121 message_route` |
| 10 | Outbound mail queue | hourly cron | `mail_mail.py:194 process_email_queue` |
| 11 | ORM event handlers | any write/create/unlink | `orm/decorators.py` — `depends`, `constrains`, `onchange`, `ondelete` |
| 12 | Frontend bootstrap | browser loads `/odoo` | `web/static/src/main.js` → `start.js` |
| 13 | CLI subcommands | operator invocation | `odoo/cli/*.py` (14 commands) |
| 14 | Addon CLI | operator invocation | `addons/iot_drivers/cli` (only addon providing one) |
| 15 | WSGI embedding | external WSGI host | `setup/odoo-wsgi.example.py` → `odoo.http.root` |
| — | **MCP server/client** | — | ✅ **none present** |

---

## 3. End-to-end flows

### Flow A — Web client request (the dominant path)

**Subsystem:** back-office web client. **Trigger:** authenticated user clicks in the UI.

```
TRIGGER
  Browser XHR → POST /web/dataset/call_kw   (session cookie)
        │
ROUTING / WSGI
  odoo/service/server.py  ThreadedServer → werkzeug → WSGI callable
        │
  odoo/http.py:2812  Application.__call__
        ├─ resets per-thread counters (query_count, perf_t0)
        ├─ applies ProxyFix if config['proxy_mode']          (:2833)
        ├─ builds HTTPRequest + Request, pushes _request_stack
        ├─ static file?  → _serve_static()
        └─ request.db set? → _serve_db()                     (:2267)
        │
REGISTRY / SESSION
  odoo/http.py:2267  _serve_db()
        ├─ Registry(self.db)                     ← per-DB cache of model classes
        ├─ registry.cursor(readonly=True)        ← starts on a READ-ONLY cursor
        ├─ registry.check_signaling(cr)          ← detects schema change by another process
        └─ env = Environment(cr, session.uid, session.context)
        │
ROUTE MATCH
  addons/base/models/ir_http.py:203  _match(path_info)
        └─ returns (rule, args); rule.endpoint.routing['readonly'] decides
           whether to keep the RO cursor or reopen read/write
        │
AUTH + DISPATCH
  odoo/http.py:2377  _serve_ir_http(rule, args)
        ├─ ir_http.py:271  _authenticate(endpoint)   ← auth='user'|'public'|'bearer'|'none'
        ├─ ir_http.py:298  _pre_dispatch(rule, args)
        ├─ Dispatcher.dispatch(endpoint, args)        ← type-specialised, odoo/http.py:2447+
        └─ ir_http.py                _post_dispatch(response)
        │
BUSINESS / DOMAIN LAYER
  Controller method → env['model'].method(...)
        └─ ORM applies, in order:
             ir.model.access  (CRUD by group)
             ir.rule          (row-level domains)
             field groups     (column visibility)
             @api.constrains  (validation)
             @api.depends     (recompute)
        │
DATA ACCESS
  odoo/orm/models.py → SQL built by the ORM
  odoo/sql_db.py:281 Cursor  ← from ConnectionPool (:610), max 64 (db_maxconn)
        │
PERSISTENCE
  PostgreSQL 17.10 @ localhost:5433 / odoo19
  Binary fields → .odoo_data/filestore  (NOT in the database)
        │
RESPONSE
  JSON payload → Dispatcher serialises → WSGI → browser
  Session written back to .odoo_data/sessions  (FilesystemSessionStore, http.py:995)
```

**Design point** ✅: the request **starts on a read-only cursor** and only upgrades to
read/write if the matched route declares `readonly=False` (`http.py:2290-2299`). This is a
deliberate scalability feature — read traffic can be routed to a replica.

---

### Flow B — External integration via JSON-2 REST

**Subsystem:** public API. **Trigger:** third-party system with a bearer token.

```
TRIGGER
  POST /json/2/res.partner/search_read
  Authorization: Bearer <api key>
        │
ROUTING
  odoo/http.py:2812 __call__ → :2267 _serve_db → ir_http._match
        │
  addons/rpc/controllers/json2.py:49
     @http.route('/json/2/<__model__>/<__method__>', methods=['POST'],
                 auth='bearer', type='json2', save_session=False)
        │
AUTH
  addons/base/models/ir_http.py:212  _auth_method_bearer()
        └─ resolves the API key → res.users.apikeys → binds env.uid
           (res_users.py:225 api_key_ids; :308 _rpc_api_keys_only)
        │
DISPATCH
  odoo/http.py — the 'json2' Dispatcher subclass
        │
DOMAIN + DATA
  env[__model__].__method__(**payload)
        └─ same ACL / record-rule / constraint stack as Flow A
        │
RESPONSE
  JSON. `save_session=False` → no session cookie issued (stateless API)
```

✅ **Confirmed:** `readonly=_web_json_2_rpc_readonly` (`json2.py:54`) — readability is
computed per call, so read-only API traffic can also stay on the RO cursor.

---

### Flow C — Legacy RPC

**Subsystem:** external integration (older clients).

```
TRIGGER   POST /xmlrpc/2/object   or   POST /jsonrpc
        │
ROUTING   addons/rpc/controllers/{xmlrpc,jsonrpc}.py
        │
SERVICE   odoo/http.py:428  dispatch_rpc(service_name, method, params)
             services: 'common' (authenticate, version), 'object' (execute_kw), 'db'
        │
AUTH      odoo/service/security.py  → check credentials / API key
        │
DOMAIN    execute_kw → env[model].method(*args, **kwargs)  → full ORM stack
        │
DATA      psycopg2 → PostgreSQL
        │
RESPONSE  XML or JSON envelope
```

⚠️ ✅ **Confirmed deprecation:** `odoo/http.py:813-815` — *"Since 19.0, `@route(type='json')`
is a deprecated alias to `@route(type='jsonrpc')"*. Custom code using `type='json'` still
works but is on notice.

---

### Flow D — Scheduled job (cron)

**Subsystem:** background processing. **Trigger:** timer, or PostgreSQL `NOTIFY`.

```
TRIGGER
  service/server.py:536  cron_thread(number)
     └─ sleeps, wakes on interval OR on PG NOTIFY (comment at :545:
        "On NOTIFY, all workers are awaken at the same time")
        │
JOB ACQUISITION  (this is the concurrency-safe part)
  base/models/ir_cron.py:187  _process_jobs(db_name)
        └─ :216  _process_jobs_loop(cron_cr, job_ids)
              └─ :308  _acquire_one_job(cr, job_id)
                    └─ row-level lock so only ONE worker runs a given job
        │
EXECUTION
  ir_cron.py:399  _process_job(cron_cr, job)
        └─ :671  _callback(cron_name, server_action_id)
              └─ executes ir.actions.server → target model method
        │
DOMAIN + DATA
  e.g. "Procurement: run scheduler" → stock.rule → creates stock.picking
       "Send invoices automatically" → account_move_send.py:816
                                        _generate_and_send_invoices()
        │
PERSISTENCE / EXTERNAL
  ORM writes → PostgreSQL
  and/or outbound: SMTP, SMS gateway, Odoo IAP
        │
OUTPUT
  No HTTP response. Side effects + ir.logging + nextcall updated on the cron row
```

✅ **Confirmed:** job acquisition uses a **row lock**, which is why running two cron threads
does not double-execute a job. ⚠️ 24 active jobs share 2 threads (`max_cron_threads = 2`).

---

### Flow E — WebSocket push (live updates)

**Subsystem:** real-time bus. **Trigger:** browser opens a socket after page load.

```
TRIGGER
  Browser → HTTP GET with `Upgrade: websocket`
     service/server.py:209,219,231 special-case the Upgrade header
     (keep-alive suppressed; raw socket handed to the handler)
        │
HANDLER
  addons/bus/websocket.py:976  WebsocketConnectionHandler
        │
SUBSCRIBE
  bus/websocket.py:390  subscribe(channels, last)
  bus/models/bus.py:212 subscribe(channels, last, db, websocket)
        │
CONSUME LOOP
  bus/websocket.py:752  _dispatch_bus_notifications()
        └─ bus/models/bus.py:171  _poll(channels, last, ignore_ids)
              └─ reads bus_bus rows > last id
        │
PRODUCER SIDE (elsewhere, any transaction)
  model._bus_send(...)  via bus_listener_mixin.py
        └─ INSERT into bus_bus  +  PostgreSQL NOTIFY
        │
OUTPUT
  Frames pushed to the browser; OWL services update the UI without polling
```

🔶 **Inferred constraint:** with `workers = 0` the websocket is served by the same threaded
server. Odoo normally dedicates `gevent_port = 8072` to this; on Windows, without gevent,
long-lived sockets consume request threads. ❓ **Unknown** how this behaves under real
concurrent load here — untested.

---

### Flow F — Inbound email becomes a record

**Subsystem:** mail gateway.

```
TRIGGER   Message fetched from a mail server  (❓ no fetchmail.server verified as configured)
        │
ROUTING   mail/models/mail_thread.py:1121  message_route(message, message_dict, …)
              └─ matches recipient against mail_alias
                 CONFIRMED live aliases:
                   info@      → crm.lead
                   sales@     → account.move
                   purchases@ → account.move
        │
PARSE     mail_thread.py:1437  message_process(model, message, custom_values)
        │
DOMAIN    mail_thread.py:1514  message_new(msg_dict, custom_values)
              └─ target model creates the record from the message
        │
DATA      crm.lead / account.move  +  mail.message  +  ir.attachment
              └─ attachment BINARY → .odoo_data/filestore
        │
OUTPUT    Optional auto-acknowledgement queued to mail.mail
```

---

### Flow G — Outbound mail queue

**Subsystem:** notification delivery. **Trigger:** hourly cron "Mail: Email Queue Manager".

```
TRIGGER   cron → mail/models/mail_mail.py:194  process_email_queue(email_ids, batch_size=1000)
        │
DOMAIN    :690  send(auto_commit=False, raise_exception=False, post_send_callback=…)
        │
EXTERNAL  base/models/ir_mail_server.py → SMTP
              (or OAuth transports: google_gmail, microsoft_outlook)
        │
DATA      mail.mail state → sent / exception;  mail.notification updated
```

**Sibling queues, same pattern:** `sms.sms` (24h), `snailmail.letter` (24h) — both dispatch
through **Odoo IAP**, i.e. paid outbound calls to Odoo SA.

---

### Flow H — Frontend bootstrap

**Subsystem:** OWL web client. **Trigger:** browser navigates to `/odoo`.

```
TRIGGER
  GET /odoo → server renders a shell page carrying odoo.__session_info__
        │
MODULE SYSTEM
  web/static/src/module_loader.js      ← Odoo's own AMD-style loader
        │
BOOTSTRAP
  web/static/src/main.js
        import { startWebClient } from "./start";
        import { WebClient } from "./webclient/webclient";
        startWebClient(WebClient);
        │
  web/static/src/start.js
        ├─ whenReady()                    (from @odoo/owl)
        ├─ localization, session, user     (@web/session, @web/core/user)
        ├─ rpc + RPCCache                  (@web/core/network/rpc)
        └─ mountComponent(...)             (from ./env.js)
        │
RUNTIME
  env.js builds the OWL env: services registry, action manager, ORM proxy
        │
DATA
  Every UI interaction → rpc() → /web/dataset/call_kw → Flow A
```

✅ **Confirmed design note:** `main.js` exists as a separate file specifically so Enterprise
can substitute a subclassed `WebClient` — stated in its own docstring.

---

### Flow I — CLI (non-server) command

**Subsystem:** operations tooling. **Trigger:** operator runs a subcommand.

```
TRIGGER   python -m odoo shell -c odoo.conf -d odoo19
        │
ROUTING   cli/command.py:109 main() → :92 find_command('shell')
        │
INIT      cli/shell.py → config.parse_config() → Registry(db)
        │
DOMAIN    Interactive REPL with `env` bound (Environment(cr, SUPERUSER_ID, {}))
        │
DATA      Same ORM + cursor stack as HTTP — no ACL bypass except via SUPERUSER_ID
        │
OUTPUT    stdout; commit is manual (cr.commit())
```

✅ 14 built-in commands: `server`, `shell`, `start`, `db`, `deploy`, `i18n`, `module`,
`populate`, `scaffold`, `cloc`, `neutralize`, `obfuscate`, `upgrade_code`, `help`.
Only one addon contributes a command: `addons/iot_drivers/cli`.

---

### Flow J — ORM event handlers (cross-cutting)

**Subsystem:** domain logic. **Trigger:** any create / write / unlink, from *any* entry point.

✅ **Confirmed** decorators in `odoo/orm/decorators.py`:

| Hook | Line | Fires |
|---|---:|---|
| `@api.depends` | 239 | Recompute stored/computed fields |
| `@api.constrains` | 83 | Validate after write; raise to abort the transaction |
| `@api.onchange` | 189 | UI-side recalculation before save |
| `@api.ondelete` | 130 | Guard unlink (with `at_uninstall` distinction) |
| `@api.autovacuum` | 299 | Register with the daily vacuum cron |

**Why this matters architecturally:** these are the *real* business-logic interception
points. A record created by cron (Flow D), by email (Flow F), by REST (Flow B) or by the UI
(Flow A) passes through the identical constraint and compute stack — there is no
"API bypass" path. The only bypass is `sudo()` / `SUPERUSER_ID`, which skips ACLs and record
rules but **still runs constraints and computes**.

---

## 4. Subsystem → representative flow index

| Subsystem | Representative flow |
|---|---|
| Web client (back office) | **A** — `call_kw` through ORM to PostgreSQL |
| Public/REST API | **B** — bearer-auth JSON-2 |
| Legacy integration | **C** — XML-RPC / JSON-RPC via `dispatch_rpc` |
| Background processing | **D** — cron acquisition and execution |
| Real-time | **E** — websocket subscribe + bus poll |
| Inbound messaging | **F** — email alias → record |
| Outbound messaging | **G** — mail/SMS/snailmail queues |
| Frontend | **H** — `main.js` → `startWebClient` |
| Operations | **I** — CLI command dispatch |
| Domain logic | **J** — ORM decorator hooks |

---

## 5. Findings and risks

### ✅ Confirmed

1. One process entry (`cli/command.py:109`); server mode is one of 14 commands
2. `ThreadedServer` is active here (`workers = 0`); Prefork/Gevent unavailable on Windows
3. Requests begin on a **read-only cursor**, upgrading only if the route requires it
4. Auth is per-route (`auth='user'|'public'|'bearer'|'none'`), applied in `ir.http._authenticate`
5. Cron jobs are acquired under a **row lock** — safe across threads/processes
6. Registry staleness is detected via a DB sequence (`registry.py:1084`), enabling multi-process coherence
7. Sessions and attachment binaries are **on the filesystem**, not in PostgreSQL
8. **No MCP server or client exists** in this codebase
9. All entry points converge on the same ORM constraint/compute stack — no bypass route

### 🔶 Inferred

1. Websocket concurrency is the weakest point on Windows — no gevent, so long-lived sockets occupy request threads
2. 24 cron jobs on 2 threads will serialise; a slow job delays unrelated ones
3. Filesystem sessions pin the deployment to a single node unless the directory is shared

### ❓ Unknown

1. Whether a `fetchmail.server` is configured — without one, Flow F never triggers
2. Real concurrency behaviour; nothing has been load-tested (zero transactions exist)
3. Whether `proxy_mode` will be enabled in front of a real proxy — currently unset, and
   enabling it without a header-scrubbing proxy would let clients spoof their source IP
4. Whether any external system currently calls Flows B or C

---

*Traced read-only from `odoo/__main__.py`, `odoo/cli/`, `odoo/service/server.py`,
`odoo/http.py`, `odoo/orm/`, `addons/base/models/ir_http.py`, `ir_cron.py`, `addons/bus/`,
`addons/mail/`, `addons/rpc/` and `web/static/src/`. No files were modified.*
