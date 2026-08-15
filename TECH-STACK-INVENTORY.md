# Technical stack inventory

**Method:** dependency manifests, actual venv contents, import scanning, vendored library
headers, configuration and infrastructure files.
**Read-only — nothing was upgraded, installed, removed or modified.**

**Criticality scale**
`CORE` — system will not boot/serve without it · `HIGH` — a major subsystem fails ·
`MED` — a feature degrades · `LOW` — optional/peripheral · `UNUSED` — no consumer found

> **Version column caveat:** "pinned" = the constraint in `requirements.txt`;
> "installed" = what is actually in `venv/` today. Where these differ it is called out.

---

## 1. Languages

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| Language | **Python** | 3.12.10 (installed); pinned `>=3.10,<3.15` | Entire backend, 8,732 files | Framework + all business logic | **CORE** | `venv` interpreter; `odoo/release.py:39-40` `MIN_PY_VERSION=(3,10)` `MAX_PY_VERSION=(3,14)` | 3.12 chosen for wheel coverage; 3.13/3.14 pins exist but are less exercised |
| Language | **JavaScript (ES modules)** | native, no transpiler | 5,887 files, web client | Front-end application | **CORE** | `web/static/src/**` | Rewritten at serve time by `odoo/tools/js_transpiler.py` — no source maps by default |
| Language | **XML** | — | 6,727 files | Views, data, QWeb + OWL templates | **CORE** | `odoo/addons/**/views`, `static/src/**/*.xml` | All modules' asset XML is merged into one document — **one malformed file blanks the whole client** |
| Language | **SCSS** | — | 1,273 files | Styling | **HIGH** | `web/static/src/scss/**` | Compiled in-process at request time |
| Language | **SQL** | PostgreSQL dialect | 78 files | Migrations, utilities | MED | `odoo/addons/**/*.sql` | — |
| Language | **PowerShell** | 5.1 | 1 file | Local dev launcher | LOW | `run-odoo.ps1` | Windows-only; no shell equivalent for Linux |

---

## 2. Runtime & process model

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| Runtime | **CPython** | 3.12.10 AMD64 | Whole app | Interpreter | **CORE** | `venv\Scripts\python.exe` | — |
| WSGI server | **Werkzeug (dev server)** | pinned & installed `3.0.1` | `odoo/service/server.py` | HTTP listener | **CORE** | `service/server.py:241` `ThreadedWSGIServerReloadable` | ⚠️ **Werkzeug's built-in server is not a production server**; `setup/odoo-wsgi.example.py` documents gunicorn instead |
| Process model | **ThreadedServer** | — | Active here | 1 HTTP listener + 2 cron threads | **CORE** | `service/server.py:451`; selected because `odoo.conf` `workers = 0` | Single process; no horizontal scaling |
| Process model | **PreforkServer / GeventServer** | — | **Unavailable** | Multi-process / async | — | `service/server.py:881`, `:767` | gevent/greenlet excluded on `sys_platform=='win32'` in `requirements.txt` — **cannot be enabled on this host** |
| Concurrency | **gevent / greenlet** | *not installed* | — | Async workers, websockets | — | `requirements.txt` platform markers | Websockets fall back to ordinary request threads |
| Windows glue | **pywin32 / pypiwin32** | `312` / `223` | Windows only | Win32 API access | MED | `requirements.txt` `pypiwin32 ; sys_platform == 'win32'` | Platform-locked |

---

## 3. Backend framework & ORM

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| Framework | **Odoo** | `19.0-20260807` | Everything | The application framework itself | **CORE** | `PKG-INFO`; `odoo/release.py:15` | In-house framework; **no third-party framework to fall back on** — expertise is Odoo-specific |
| ORM | **Odoo ORM (in-house)** | ships with 19.0 | `odoo/orm/` | Models, fields, domains, ACLs | **CORE** | `orm/registry.py`, `models.py`, `fields_*.py` | Not SQLAlchemy; PostgreSQL-only, not portable |
| DB driver | **psycopg2** | pinned & installed `2.9.9` | `odoo/sql_db.py` | PostgreSQL adapter | **CORE** | `sql_db.py:281 Cursor`, `:610 ConnectionPool` | `psycopg2` (not `-binary`) — needs build toolchain on some platforms |
| Templating | **QWeb (in-house)** | ships with 19.0 | Server-side reports/pages | Template engine | **CORE** | `base/models/ir_qweb.py` | — |
| Templating | **Jinja2** | pinned & installed `3.1.2` | 1 file | Peripheral templating | LOW | 1 import under `odoo/` | Near-unused; kept for compatibility |
| Sandboxing | **safe_eval (in-house)** | ships with 19.0 | Server actions, domains | Evaluates user-stored Python | **HIGH** | `odoo/tools/safe_eval.py` | ⚠️ Security-sensitive by design — any escape is an RCE |

---

## 4. Frontend

All frontend libraries are **vendored into the repository** — there is no npm, no
`package.json`, and no lockfile anywhere.

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| Framework | **OWL** | ships with Odoo (no header version) | Whole web client | Reactive component framework | **CORE** | `web/static/lib/owl/`; `@odoo/owl` imports | Odoo-specific; small ecosystem, few external devs |
| Bootstrap | **module_loader** (in-house AMD) | — | Client boot | Module resolution | **CORE** | `web/static/src/module_loader.js` | — |
| Entry | `main.js` → `start.js` | — | `/odoo` page load | Mounts `WebClient` | **CORE** | `web/static/src/main.js` | Separated so Enterprise can swap `WebClient` |
| CSS framework | **Bootstrap** | bundled (no header version) | All backend + website UI | Layout & components | **HIGH** | `web/static/lib/bootstrap/` | Vendored — cannot be patched via npm audit |
| Charting | **Chart.js** | **4.4.5** | Graph views, dashboards | Charts | MED | `web/static/lib/Chart/Chart.js` header | — |
| Charting adapter | chartjs-adapter-luxon | bundled | Time-axis charts | Date handling for Chart.js | MED | `web/static/lib/chartjs-adapter-luxon/` | — |
| Date/time | **Luxon** | bundled | Date fields, calendar | Date maths & formatting | **HIGH** | `web/static/lib/luxon/` | Used by the custom BS date widget too |
| Calendar UI | **FullCalendar** | bundled (core, daygrid, interaction, list) | Calendar views | Calendar rendering | MED | `web/static/lib/fullcalendar/` | — |
| DOM utility | **jQuery** | **3.6.3** | Legacy areas, website | DOM manipulation | MED | `web/static/lib/jquery/jquery.js` header | ⚠️ Legacy; 3.6.3 is behind current 3.7.x |
| Positioning | **Popper.js** | **2.11.8** | Dropdowns, tooltips | Overlay positioning | MED | `web/static/lib/popper/` | Bootstrap dependency |
| Sanitisation | **DOMPurify** | bundled | HTML fields, editor | XSS prevention | **HIGH** | `web/static/lib/dompurify/` | ⚠️ Security-critical and **vendored** — patching depends on Odoo releases |
| PDF | **PDF.js** | bundled | In-browser PDF preview | PDF rendering | MED | `web/static/lib/pdfjs/` | Historically CVE-prone; vendored |
| Code editor | **Ace** | bundled | Developer/technical views | Code editing | LOW | `web/static/lib/ace/` | — |
| Barcode | **zxing-library** | bundled | POS, inventory scanning | Camera barcode decoding | MED | `web/static/lib/zxing-library/` | — |
| Diffing | diff_match_patch | bundled | HTML editor | Text diff | LOW | `web/static/lib/diff_match_patch/` | — |
| Signature | signature_pad | bundled | Portal signing | Signature capture | LOW | `web/static/lib/signature_pad/` | — |
| Syntax | prismjs | bundled | Code display | Highlighting | LOW | `web/static/lib/prismjs/` | — |
| Errors | stacktracejs | bundled | Client error reporting | Stack normalisation | LOW | `web/static/lib/stacktracejs/` | — |
| Icons | odoo_ui_icons | bundled | UI | Icon font | LOW | `web/static/lib/odoo_ui_icons/` | — |

---

## 5. Databases & data stores

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| RDBMS | **PostgreSQL** | **17.10** (server) | Everything | Primary datastore | **CORE** | `SELECT version()` on `localhost:5433` | Instance also hosts unrelated `ist_datahub` DB |
| Connection pool | Odoo `ConnectionPool` | in-house | `odoo/sql_db.py:610` | Pooling | **CORE** | `odoo.conf` `db_maxconn = 64` | No PgBouncer; pool is per-process |
| Object store | **Filesystem filestore** | — | `.odoo_data/filestore/odoo19` | Attachment binaries | **CORE** | `odoo.conf` `data_dir` | ⚠️ **Not in the DB** — `pg_dump` alone loses all attachments |
| Session store | **FilesystemSessionStore** | — | `.odoo_data/sessions` | Server-side sessions | **HIGH** | `odoo/http.py:995` | Pins deployment to one node unless shared |
| Asset cache | `ir.attachment` + filestore | — | Compiled JS/CSS bundles | Build cache | **HIGH** | `base/models/assetsbundle.py` | Stale bundles observed in practice; cleared by deleting attachments |

---

## 6. Caching

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| In-process cache | **Odoo `ormcache` / LRU** | in-house | ORM, registry | Method/result memoisation | **HIGH** | `odoo/tools/lru.py`; `orm/registry.py` cache sequences | Per-process — **not shared** across workers |
| Cache invalidation | DB sequence signalling | in-house | Multi-process coherence | Detect stale registry/cache | **HIGH** | `orm/registry.py:1084` `get_sequences()`, `check_signaling()` | Polling-based, not push |
| External cache | **Redis / Memcached** | **NOT PRESENT** | — | — | — | No match in `requirements.txt` | No distributed cache — a scaling ceiling |

---

## 7. Message brokers & queues

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| Broker | **None** (no Kafka/RabbitMQ/Celery/AMQP) | — | — | — | — | No match for `redis\|celery\|rabbit\|kafka\|pika\|amqp` in `requirements.txt` | All async work is DB-backed |
| Pub/sub | **PostgreSQL `NOTIFY` + `bus_bus` table** | — | `addons/bus/` | Real-time push to browsers | **HIGH** | `bus/models/bus.py:171 _poll`, `:212 subscribe`; `service/server.py:545` NOTIFY comment | Database *is* the message bus — bus traffic hits PG |
| Job queue | **`ir.cron` table** | — | 24 active jobs | Scheduled/background work | **HIGH** | `base/models/ir_cron.py:187 _process_jobs`, `:308 _acquire_one_job` (row lock) | ⚠️ 24 jobs share **2** threads (`max_cron_threads = 2`) |
| Outbound queues | `mail.mail`, `sms.sms`, `snailmail.letter` | — | Drained by crons | Deferred delivery | **HIGH** | `mail/models/mail_mail.py:194 process_email_queue` | Hourly drain — not near-real-time |
| Transport | **WebSocket** | — | `addons/bus/websocket.py:976` | Live UI updates | MED | `WebsocketConnectionHandler` | Without gevent, consumes request threads |

---

## 8. Authentication & authorization

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| Password hashing | **passlib** | pinned & installed `1.7.4` | `res.users` | Credential storage | **CORE** | 6 imports under `odoo/` | — |
| Crypto | **cryptography** | pinned & installed `42.0.8` | TLS, signing, hashing | Primitives | **CORE** | `requirements.txt:14` | Pinned for CVE fixes; **do not float** |
| Crypto | **pyOpenSSL** | pinned & installed `24.1.0` | Certificate handling | TLS glue | **HIGH** | `requirements.txt:65` | Pinned to match `cryptography==42.0.8` |
| WebAuthn | **cbor2** | pinned & installed `5.6.2` | `auth_passkey` | Passkey encoding | **HIGH** | 5 imports; `auth_passkey` **installed** | — |
| Certificates | **asn1crypto** | pinned & installed `1.5.1` | X.509 parsing | Certificate structures | MED | 4 imports | — |
| 2FA | **`auth_totp`** (+`_mail`,`_portal`) | Odoo module | Login | TOTP second factor | **HIGH** | `ir_module_module` = installed | — |
| Passkeys | **`auth_passkey`** (+`_portal`) | Odoo module | Login | WebAuthn | **HIGH** | installed | — |
| Signup | **`auth_signup`** | Odoo module | Portal | Self-registration | MED | installed | Public account creation is enabled |
| API keys | `res.users.apikeys` | in-house | RPC + JSON-2 bearer | Machine auth | **HIGH** | `res_users.py:225`, `:308`; `ir_http.py:212 _auth_method_bearer` | — |
| **Not installed** | `auth_oauth`, `auth_ldap`, `auth_password_policy` (×3), `auth_timeout` | — | — | SSO, directory, policy, idle logout | — | `ir_module_module` = uninstalled | ⚠️ **No password-strength policy and no session timeout are active** |
| Authorization | ACLs / record rules / field groups | in-house | Every model | 4-layer access control | **CORE** | `ir.model.access.csv`; `base/models/ir_rule.py` | Bypassed by `sudo()` — audit custom usage |

---

## 9. AI / LLM libraries

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| AI / LLM | **NONE** | — | — | — | — | Case-insensitive scan of `requirements.txt` + `setup.py` for `openai\|anthropic\|langchain\|transformers\|llama\|huggingface\|tiktoken\|torch\|tensorflow\|scikit\|numpy\|pandas` → **zero matches** | No ML/AI stack of any kind — also **no numpy/pandas**, so no data-science tooling |
| MCP | **NONE** | — | — | — | — | Scan for `modelcontextprotocol\|mcp_server\|mcp_client\|"mcp"` across all `.py/.js/.json/.md` → **zero matches** | — |

---

## 10. API clients & outbound integration libraries

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| HTTP client | **requests** | pinned & installed `2.31.0` | All outbound calls | REST/HTTP client | **CORE** | `requirements.txt:88` | — |
| HTTP stack | **urllib3** | pinned & installed `2.0.7` | Transitive | Connection handling | **CORE** | `requirements.txt:93` | Pinned for `cryptography` compatibility |
| SOAP | **zeep** | pinned & installed `4.2.1` | 12 files incl. `base/models/res_company.py`, `odoo/tools/zeep/` | SOAP/WSDL client | MED | import scan | Odoo ships its own `tools/zeep` wrapper |
| GeoIP | **geoip2 / maxminddb** | `2.9.0` / `3.1.1` | `odoo/http.py`, `test_http/utils.py` | Request geolocation | LOW | import scan | ❓ Requires a MaxMind DB file — presence unverified |
| Phone | **python-stdnum** | `1.19` | VAT/IBAN/ID validation | Standard-number checks | MED | `requirements.txt` | — |
| iCal | **vobject** | `0.9.6.1` | 7 files, `calendar` | iCalendar generation | MED | import scan | — |
| HTML | **beautifulsoup4 / soupsieve** | `4.15.0` / `2.9.2` | 2 files | HTML parsing | LOW | import scan | Transitive via ofxparse |
| XML/HTML | **lxml** + **lxml_html_clean** | `5.2.1` / `0.4.4` | Views, QWeb, sanitising | XML engine | **CORE** | `requirements.txt` | `lxml_html_clean` split out from lxml ≥5 |

---

## 11. Document generation

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| PDF | **reportlab** + **rl-renderPM** | `4.1.0` / `4.0.3` | 4 files, reports | PDF primitives | **HIGH** | import scan; `rl-renderPM` is win32-only pin | — |
| PDF | **PyPDF2** | pinned & installed `2.12.1` | PDF merge/stamp | PDF manipulation | **HIGH** | `requirements.txt:67` | ⚠️ **PyPDF2 is deprecated upstream** (succeeded by `pypdf`); Odoo already uses `PyPDF>=5.4.0` on Python 3.13 |
| PDF engine | **wkhtmltopdf** | **0.12.6 (with patched qt)** | Report rendering | HTML→PDF | **HIGH** | Installed 2026-08-15 into `.runtime/bin/wkhtmltopdf/` (gitignored), wired via `bin_path`; verified by rendering a real posted invoice to a 27 KB PDF | ⚠️ Dev host only — the server is still unprovisioned. Upstream archived 2023; last Windows build is 0.12.6-1 (2020) and ships no checksum. See **DEP-6** |
| Excel | **openpyxl** / **XlsxWriter** | `3.1.2` / `3.1.9` | 4 / 6 files | xlsx read/write | MED | import scan | — |
| Excel (legacy) | **xlrd** / **xlwt** | `2.0.1` / `1.3.0` | 3 / 3 files | Legacy .xls | LOW | import scan | ⚠️ Both effectively unmaintained; `xlwt` writes the obsolete BIFF format |
| Images | **Pillow** | `10.2.0` | 24 files | Image processing | **HIGH** | import scan | Frequent CVE target — keep pinned deliberately |
| QR / barcode | **qrcode** + **pypng** | `7.4.2` / `0.20220715.0` | 3 files | QR generation | MED | import scan | — |
| Docs | **docutils** | `0.20.1` | 4 files | reStructuredText in manifests | LOW | import scan | — |
| Numbers | **num2words** | `0.5.13` | 5 files | Amount-in-words on invoices | MED | import scan | — |

---

## 12. Logging, monitoring, observability

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| Logging | **Python stdlib `logging`** | — | Whole app | Application logging | **CORE** | `odoo/netsvc.py`, `odoo/logging.py`, `loglevels.py` | Plain text, not structured/JSON |
| Log destination | **stderr only** | — | — | — | — | `odoo.conf` sets `log_level`/`log_handler` but **no `logfile`** | ⚠️ Logs lost unless the caller redirects |
| In-DB logs | `ir.logging` | — | `base/models/ir_logging.py` | Client/server log records | LOW | file exists | — |
| Profiling | **Odoo profiler + speedscope** | in-house | `odoo/tools/profiler.py`, `speedscope.py`, `ir_profile.py` | Flamegraph profiling | MED | files exist | Manual, on-demand only |
| Resource watchdog | in-house limits | — | `service/server.py` | `limit_time_real`, memory caps | MED | observed `virtual real time limit (153/120s) reached` | Fires under load already |
| Process metrics | **psutil** | `5.9.8` | 4 files | Memory/CPU limits | MED | import scan | — |
| APM / metrics / tracing | **NONE** | — | — | — | — | No `sentry\|prometheus\|opentelemetry\|statsd\|datadog\|newrelic` in `requirements.txt` | ⚠️ **No error tracking, no metrics endpoint, no health check** |

---

## 13. Testing

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| Test framework | **Odoo test framework** (on `unittest`) | ships with 19.0 | 422 test packages | Tagged test running | **HIGH** | `odoo/tests/` — `case.py`, `common.py`, `suite.py`, `tag_selector.py` | Not pytest — pytest tooling/plugins don't apply |
| Form simulation | `odoo.tests.form` | — | Computed-field tests | Replays onchange cycle | MED | `odoo/tests/form.py` | — |
| Browser tests | **headless Chrome via CDP** | Chrome 151.0.7922.76 (host) | `HttpCase.browser_js` | End-to-end UI tests | MED | `odoo/tests/common.py:1247 ChromeBrowser`, `:2450 browser_js` | Chrome version is whatever the host has — not pinned |
| CDP transport | **websocket-client** | installed `1.9.0` | 6 files | DevTools protocol | MED | import scan | ⚠️ **Installed but NOT in `requirements.txt`** — absence silently skips browser tests |
| Time mocking | **freezegun** | pinned `1.2.1`, installed `1.2.1` | Test suites | Freeze time | MED | `setup.py:74 tests_require` | Declared in `tests_require`, not `requirements.txt` |
| JS unit tests | **QUnit / Hoot** | bundled | `web/static/lib/qunit`, `hoot`, `hoot-dom` | Front-end tests | MED | vendored libs | — |
| Local suite | `l10n_np_bs` tests | — | `custom_addons/l10n_np_bs/tests/` | XML validity, BS conversion, render | MED | `test_calendar_ui.py` | The only project-authored tests |

---

## 14. Build tools

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| Packaging | **setuptools** | installed `83.0.0` | `setup.py` | sdist/install | **HIGH** | `setup.py`, `setup.cfg` | No `pyproject.toml` / PEP 517 backend |
| Packaging | **wheel** | installed `0.47.0` | Build | Wheel format | MED | venv | — |
| Asset pipeline | **libsass** | `0.22.0` | 1 import (`sass`) | SCSS → CSS at runtime | **CORE** | `base/models/assetsbundle.py` | Compilation happens **in the request path** |
| Asset pipeline | **rjsmin** | `1.2.0` | 1 import | JS minification | **CORE** | `assetsbundle.py` | — |
| JS transform | `js_transpiler.py` | in-house | Serve time | Module syntax rewrite | **CORE** | `odoo/tools/js_transpiler.py` | — |
| Codemods | `odoo/upgrade_code/` | ships with 19.0 | Version migration | Automated source rewrites | MED | 9 scripts, `cli/upgrade_code.py` | — |
| Package build driver | `setup/package.py` | — | deb/rpm/docker builds | Release packaging | **UNUSED** | references `setup/package.df*`, `setup/rpm/odoo.spec`, `debian/` — **all absent** | ⚠️ **Dead code in this distribution** |
| Node / npm | **NONE** | — | — | — | — | No `package.json` anywhere | Frontend deps are vendored; no `npm audit` possible |

---

## 15. CI/CD, containers, cloud, IaC

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| CI/CD | **NONE** | — | — | — | — | Absent: `.github/`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml`, `.travis.yml`, `.circleci/`, `bitbucket-pipelines.yml`, `.drone.yml` | ⚠️ **Nothing verifies a change before it runs** |
| Containers | **NONE** | — | — | — | — | `find -maxdepth 3` for `Dockerfile*`/`docker-compose*` → zero | Build driver expects Dockerfiles that aren't shipped |
| IaC | **NONE** | — | — | — | — | No `*.tf`, no Ansible, no Helm, no `Makefile` | — |
| Cloud services | **NONE configured** | — | — | — | — | No AWS/GCP/Azure SDK in `requirements.txt` | Only outbound SaaS is **Odoo IAP** (see below) |
| SaaS dependency | **Odoo IAP** | — | `iap`, `iap_crm`, `iap_mail`, `crm_iap_enrich`, `crm_iap_mine`, `partner_autocomplete` | Metered paid services (SMS, snailmail, lead enrichment) | MED | modules installed; cron "CRM: enrich leads (IAP)" 24h | ⚠️ **Phones home to Odoo SA on a schedule** — fails noisily in egress-restricted networks |
| Deployment template | `setup/odoo-wsgi.example.py` | — | Documentation only | gunicorn/uwsgi example | LOW | file exists | Not wired to anything |
| Service unit | IoT systemd unit | — | `iot_box_image/.../odoo.service` | IoT box only | LOW | file exists | **Not** a server deployment template |

---

## 16. Security tooling

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| Linting | **flake8** config | — | `setup.cfg:4` | Style/lint config present | LOW | `setup.cfg` `[flake8]` section | Config exists; flake8 itself **not installed** |
| SAST / SCA | **NONE** | — | — | — | — | No `bandit\|safety\|pip-audit\|semgrep\|trivy\|snyk` in `requirements.txt`/`setup.cfg` | ⚠️ No dependency-vulnerability scanning of any kind |
| CAPTCHA | `google_recaptcha` | Odoo module | Public forms | Bot protection | MED | installed; used by `website/controllers/form.py:31` | Substitutes for CSRF on that route (`csrf=False`) |
| Privacy | `privacy_lookup` | Odoo module | Subject-access requests | GDPR-style lookup | LOW | installed | Suggests personal data was anticipated |
| Secrets management | **NONE** | — | — | — | — | `odoo.conf` holds `db_password`, `admin_passwd` in plaintext | ⚠️ No vault, no env-var indirection in use |

---

## 17. Custom / project-specific

| Category | Technology | Version | Where used | Purpose | Criticality | Evidence | Potential concern |
|---|---|---|---|---|---|---|---|
| Custom module | **`l10n_np_bs`** | `19.0.1.0.0` | `custom_addons/` | Bikram Sambat calendar + date widget | MED | `__manifest__.py`; installed | Only project-authored Odoo module |
| Custom dep | **nepali-datetime** | installed `1.0.8.5` | `l10n_np_bs/tools/bs.py` | BS↔AD conversion table | **HIGH** (for that module) | `__manifest__.py` `external_dependencies`; 0 imports under `odoo/`, imported from `custom_addons/` | ⚠️ **Not in any pip-readable file** — fresh installs will break |
| Custom toolchain | **`l10n_ne/`** | — | Repo root | Nepali translation build scripts | MED | `l10n_ne/apply.py`, `translations.py` | Not an Odoo module (no manifest); writes into the vendor tree |

---

## 18. Unused, duplicated, outdated

### Apparently unused

| Dependency | Evidence | Assessment |
|---|---|---|
| **ofxparse** `0.21` | **0 imports** anywhere under `odoo/` (verified with correct module name) | Consumed by OFX bank-statement import, which is not in this distribution. **Vestigial** |
| **pyusb** `1.2.1` (`import usb`) | Only `addons/iot_drivers/iot_handlers/` — module **not installed** | Unused at runtime here |
| **pyserial** `3.5` (`import serial`) | Only `addons/iot_drivers/` drivers — **not installed** | Unused at runtime here |
| **Jinja2** `3.1.2` | 1 import under `odoo/` | Near-unused; QWeb is the real engine |
| **geoip2 / maxminddb** | Imported by `odoo/http.py`, but requires a MaxMind database file | ❓ Effectively inert if the DB file is absent — **Needs Verification** |
| `setup/package.py` | References 6 files that don't exist | **Dead code** |

### Outdated / deprecated

| Item | Current | Concern |
|---|---|---|
| **PyPDF2** `2.12.1` | Deprecated upstream in favour of `pypdf` | Odoo already ships `PyPDF>=5.4.0` for Python 3.13 — this venv is on the legacy path |
| **xlwt** `1.3.0` | Unmaintained; writes obsolete BIFF `.xls` | Legacy export only |
| **xlrd** `2.0.1` | Dropped `.xlsx` support in 2.0 | Reading modern Excel needs openpyxl |
| **jQuery** `3.6.3` | Behind current 3.7.x | Vendored — cannot be updated independently of Odoo |
| **Werkzeug dev server** | In use as the HTTP server | Not intended for production |
| 62 × `i18n/ne.po` | Odoo 11 (2017) headers, **0 translated strings** | Look like Nepali support; provide none |

### Duplicated

| Item | Evidence | Concern |
|---|---|---|
| **87 `.po` files stored twice** | `l10n_ne/po/*.po` (87) and `odoo/addons/*/i18n_extra/ne.po` (87) | No enforced sync; drift is undetectable |
| **Two Excel read paths** | `xlrd` + `openpyxl` both installed | Historical, both in use |
| **Two PDF paths** | `reportlab` (primitives) + `PyPDF2` (manipulation) | Not true duplication; different roles |
| **pywin32 + pypiwin32** | `312` and `223` installed | `pypiwin32` is a legacy alias wrapper for `pywin32` |

### Declared-but-undeclared drift

| Package | Installed | In `requirements.txt`? | Impact |
|---|---|---|---|
| `nepali-datetime` `1.0.8.5` | ✅ | ❌ | Custom module fails on a clean install |
| `websocket-client` `1.9.0` | ✅ | ❌ | Browser tests silently skip |
| `freezegun` `1.2.1` | ✅ | ⚠️ only in `setup.py` `tests_require` | Not installed by `pip install -r requirements.txt` |

---

## Summary of the highest-consequence concerns

1. **No CI/CD, no containers, no IaC** — nothing validates a change before it runs
2. **wkhtmltopdf is unmaintained** (**DEP-6**) — installed and working on the dev host since 2026-08-15, but upstream was archived in 2023, the last Windows build dates from 2020, it ships no checksum, and Odoo 19 offers no alternative engine
3. **Two undeclared runtime dependencies** — a clean rebuild will not reproduce this environment
4. **No APM, metrics, health check or dependency scanning** — no operational or supply-chain visibility
5. **Werkzeug dev server + `workers = 0`** — single-process, not a production posture
6. **All frontend libraries vendored, no npm** — `npm audit` impossible; DOMPurify and PDF.js (both security-relevant) can only be patched by upgrading Odoo
7. **Secrets in plaintext**, no vault, `list_db = True` with a default master password
8. **No password policy and no session timeout modules installed**

---

*Compiled read-only from `requirements.txt`, `setup.py`, `setup.cfg`, `odoo.conf`, the live
`venv/` contents, import scanning across `odoo/`, vendored library headers in
`web/static/lib/`, and `ir_module_module`. **Nothing was upgraded, installed or removed.***
