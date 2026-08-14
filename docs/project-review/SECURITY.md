# Security

Findings by ID in [`BACKLOG.md`](BACKLOG.md). **No secret values are reproduced here** — they are
referenced by location only.

Calibrated for **production with real client data**, **multi-company**, **multi-tenant SaaS
planned**. Cross-tenant exposure is treated as P0 throughout.

## Posture

**The application layer is sound. The perimeter is not.**

No SQL injection anywhere, no dangerous execution primitives, every model covered by an ACL, and
a formula evaluator that genuinely blocks arbitrary code execution with a test proving it. Those
are real strengths and they were verified individually rather than sampled.

The exposure is concentrated in configuration and in the request-routing layer — and one of those
findings is a **live one-request cluster takeover**.

## The one to fix today — SAAS-2

`/web/database/create` is `auth="none"`, `csrf=False`, and begins:

```python
insecure = odoo.tools.config.verify_admin_password('admin')
if insecure and master_pwd:
    dispatch_rpc('db', 'change_admin_password', ["admin", master_pwd])
```

The same block appears on `duplicate`, `drop`, `backup` and `restore`.

**I verified `verify_admin_password('admin')` returns `True` on this instance.** The branch is
armed. One unauthenticated POST sets the **cluster** master password to an attacker's value, and
that password then authorises backup — a full `pg_dump` plus filestore zip — of every database.

No rate limit, no lockout, no CSRF, no audit trail beyond a log line. `crypt_context` registers a
`plaintext` scheme, so the shipped value verifies as-is.

**Only `http_interface = 127.0.0.1` prevents this today. SaaS is precisely what removes that.**
Effort to fix: XS. Do it before anything else in this document.

## Tenant isolation

Full analysis in [`SAAS_MULTI_TENANCY.md`](SAAS_MULTI_TENANCY.md). The security-relevant summary:

| Finding | What it permits |
|---|---|
| **SAAS-1** | With `dbfilter` unset, an `X-Odoo-Database` header selects any tenant from any host with no cookie |
| **SAAS-3** | `proxy_mode` makes client-supplied `X-Forwarded-Host` authoritative for routing, and the documented nginx does not pin it |
| **SAAS-4** | `authenticate(db=…)` and `?db=` are gated **only** by `db_filter` — one regex is the whole boundary |
| **SAAS-5** | The shared session directory permits cross-tenant session **destruction**; upstream's own comment names the attack, and the guard checks format and path prefix but **never ownership** |
| **SAAS-6** | `list_db = True` with `dbfilter` unset in both dev configs |

**What holds even so:** reaching another tenant's registry does **not** read its data. Auth is
still required, and a session token from tenant A cannot validate in tenant B because the HMAC key
includes a per-database `database.secret`. SAAS-1 and SAAS-4 are therefore **reachability**
findings — they hand an attacker the full authenticated attack surface of every tenant, which is
serious, but they are not direct data reads. That distinction is worth keeping precise.

## Secrets

| ID | Issue |
|---|---|
| **SEC-1** | The live master and database passwords are committed to a tracked document (`RECONNAISSANCE.md:232,236,480`, commit `e4ff7dab`) — the actual values, not placeholders. The document flags them as critical while being the vehicle that publishes them |
| **SAAS-2 / OPS-2** | One master password for the whole cluster, currently the product default, with `list_db = True` |
| **DAT-1** | `odoo.conf`, two full database dumps, the filestore and 75 live session files sit in corporate OneDrive sync |

**Rotation is unavoidable** — the values are in immutable history, so deleting the file does not
undo it. Rotate first; that is what reduces risk. History rewriting is a separate, later decision,
and is cheapest **before** the first push (SUP-2).

**Working correctly:** `odoo.conf` was never committed (`.gitignore:38` verified effective). Both
templates use placeholders. No API keys, tokens or private keys anywhere in scope.

## Authorization

**SEC-2 (P1) — no record rules on any local model.** Zero `ir.rule` records exist across the eight
modules, while ten new models carry `company_id`. Odoo does not synthesise multi-company rules;
every *vendored OCA* module ships one.

In a multi-company database, company A's accountant reads and edits company B's loans, TDS
schedule, VAT return forms and filed returns. Business logic filters by company, so computed
figures are right — the **records** are exposed. This is the finding that becomes acute the moment
a second company or tenant exists.

**SEC-6 (P2) — the read-only accounting role can rewrite a filed VAT return.**
`l10n_np_vat_return/security/ir.model.access.csv:8` grants `group_account_readonly`
write/create/unlink on return lines, inconsistent with the same file's own read-only rows for the
form and box. One-character fix.

**SEC-5 (P2)**, vendored OCA: `base.group_user` — every internal employee — has CRUD on budget
lines and on the persistent age-report configuration model.

**Verified clean:** every concrete model has an ACL; the uncovered ones are `AbstractModel`s and
abstract report models, correctly exempt. Menu-level `groups=` gating is consistent with the ACLs.

## Privilege escalation

Every `sudo()` in scope was read and classified.

**Justified.** The lock-dates wizard checks `group_account_manager` immediately before writing,
touches only five allowlisted fields, and leaves core's hard-lock irreversibility check intact —
defence in depth on an already-restricted ACL. The asset module elevates solely to *detect a
blocking condition and refuse*, which is the correct direction. `report_xlsx` uses `sudo(False)`
to **de-escalate** before rendering so record rules still apply to data — the right pattern.

**Not justified — SEC-4 (P2).** `abstract_wizard.py:67-75` writes a global `ir.default`
(`user_id=False`) under `sudo()` on every Export click, and the wizards are open to
`base.group_user`. Bounded to one integer, but a genuine privilege crossing with no guard.
Vendored — override locally.

No `with_user()` anywhere. `SUPERUSER_ID` appears only in `l10n_ne/apply.py`, an operator-run
offline CLI with no network exposure — though note it calls `cr.commit()` explicitly with no
dry-run by default.

## Injection and evaluation

**No SQL injection.** Every `cr.execute()` in `custom_addons` was read individually and is
parameterised — including the only one built from record data (`date_range/models/date_range.py:72-93`)
and the tax query in `journal_ledger.py:217`, whose parameters come from `tuple(move_lines.ids)`.
No f-strings, `%` formatting, `.format()` or concatenation into any SQL string.

**SEC-3 (P2) — the VAT formula evaluator.** The guard substitutes values first, then requires
`re.fullmatch(r"[0-9eE+\-*/(). ]*")` with `__builtins__` emptied.

*What it gets right, verified:* no identifier, underscore, quote or bracket survives, so arbitrary
code execution is genuinely blocked — and a test proves it against an `__import__` payload.

*What it misses, verified:* `*` is whitelisted, so `**` is too. I confirmed `9**9**9` passes
`fullmatch`. It evaluates to a ~370-million-digit integer, hanging the worker before `except` can
run. On the Windows config (`workers = 0`, `limit_time_real = 0`) that takes the whole server
down. Privileged-user DoS, not anonymous. One-character fix plus a test.

**SEC-9 (P3)** — `report_xlsx_helper` uses `eval()` with **full builtins**. Safe today: every call
site was traced and column specs come only from Python report classes. The invariant is a code
comment, unenforced — any future config-sourced spec turns it into authenticated RCE.

**Absent entirely:** `exec`, `os.system`, `subprocess`, `pickle`, `yaml.load`.

## Web surface

Only two controllers exist, both vendored; **no locally written module defines an HTTP route.**

**SEC-8 (P2)** — bare `@route()` overrides inherit auth invisibly (authenticated today because
core is, but silently tracks upstream across upgrades); client-controlled `context` is merged into
report rendering (mitigated by `sudo(False)`); `_serialize_exception` is returned to the client —
information disclosure, escaped, so not XSS.

`docids` is coerced with `int()` in both controllers. No `t-raw`; the single `Markup()` wraps a
static string.

**SAAS-10 (P2)** — `/web/database/manager` renders publicly even with `list_db = False`; there is
no route-level guard, and `_render_template` falls back to `[request.db]`. It leaks server
version, language and country lists, the `insecure` flag and the current database name — plus a
public master-password form. **Block `/web/database/` at the reverse proxy**; the documented nginx
does not.

## Filesystem

**SEC-7 (P2)** — `l10n_ne/apply.py` joins `--modules` from argv into `os.path.join(ADDONS, …)`
unvalidated for both read and write; no normalisation, no containment check, no `..` rejection.
Operator-run, so the caller already has write access — the issue is an unguarded footgun in a tool
documented for routine use. `os.path.commonpath` containment is a two-line fix.

**SEC-11 (P3)** — `sys.path` is prepended before importing `polib`; a planted `polib.py` would
shadow it. Requires repo write access — which, per DAT-1, is a cloud-synced directory.

## Configuration and infrastructure

| ID | Issue |
|---|---|
| SAAS-2 / OPS-2 | Default master password + `list_db = True` |
| SAAS-1 / SAAS-6 | `dbfilter` unset |
| SAAS-3 | `proxy_mode` with unpinned `X-Forwarded-Host` |
| OPS-4 | `limit_time_real = 0` removes the runaway-request watchdog — a cross-tenant availability path once shared |
| DAT-1 | Client data and credentials in cloud sync |
| OPS-3 | Service account owns `/opt/odoo` including its own venv; `ProtectSystem=full` leaves `/opt` writable, so a code-execution bug becomes persistent. Missing `PrivateDevices`, `RestrictAddressFamilies`, `SystemCallFilter`, `MemoryMax`, `UMask`; account created with `-s /bin/bash` |
| PG-1/2/4 | Odoo account can reach an unrelated database; PUBLIC CONNECT and PUBLIC CREATE defaults |

**Working correctly:** `http_interface = 127.0.0.1` everywhere; `dev_mode` commented out and
gated behind an explicit flag in both launchers; no `smtp_*` in any config (SAAS-9 stays
untriggered); the Linux template is materially safer than the dev one with every delta tabulated
and explained; the systemd unit is above average (`NoNewPrivileges`, `ProtectHome`, `PrivateTmp`,
scoped `ReadWritePaths`).

## Remediation order

1. **SAAS-2 + OPS-2** — strong master password, `list_db = False`, block `/web/database/*`. Hours.
2. **SEC-1** — rotate both credentials.
3. **SAAS-1 + SAAS-4 + SAAS-11** — anchored `dbfilter`.
4. **SAAS-3** — pin `X-Forwarded-Host` in nginx.
5. **DAT-1** — client data and credentials out of cloud sync.
6. **SEC-2** — record rules, **before** a second company or tenant exists.
7. **SEC-6**, **SEC-3**, **SEC-7** — small, contained fixes.
8. **PG-1, PG-2, PG-4** — revokes, and bake them into provisioning.
9. **OPS-3, OPS-4** — systemd hardening and the watchdog, once the writable-`/opt` question is decided.
10. **SEC-4, SEC-5, SEC-8, SEC-9** — vendored OCA; override locally or report upstream. **Do not
    edit in place** — that destroys the zero-drift property protecting LIC-1.
