# Security

Findings by ID in [`BACKLOG.md`](BACKLOG.md). **No secret values are reproduced here** — they are
referenced by location only.

Calibrated for **production with real client data**, **multi-company**, **multi-tenant SaaS
planned**. Cross-tenant exposure is treated as P0 throughout.

> ## Status, 2026-08-23 — read this before anything below
>
> **Six findings in this document are now RESOLVED**, and until today this file still described
> all of them as live. That was the most misleading kind of staleness: a reader would have
> concluded the cluster master password was still `admin` and that one unauthenticated POST could
> take the cluster, a state that ended on 2026-08-22.
>
> | ID | Status | Closed by |
> |---|---|---|
> | **SAAS-2** | RESOLVED 2026-08-22 | Master password rotated to a 32-character random value, stored hashed. `verify_admin_password('admin')` is now **False**, so the takeover branch is unreachable |
> | **SEC-1** | RESOLVED 2026-08-22 | Both published credentials rotated; `RECONNAISSANCE.md` redacted. History deliberately not rewritten — the leaked values were the defaults `admin` and `odoo`, worthless once rotated |
> | **OPS-2** | RESOLVED 2026-08-22 | `list_db = False` |
> | **SEC-2** | RESOLVED 2026-08-23 | Ten global `ir.rule` records; proved by negative control |
> | **SEC-6** | RESOLVED 2026-08-23 | Read-only role is now read-only on return lines; billing and manager have their own rows |
> | **SEC-3** | RESOLVED 2026-08-23 | The formula evaluator parses and walks an AST instead of calling `eval` |
>
> Each section below now carries its own resolution note. **The remediation order at the end has
> been renumbered** so closed items are struck rather than presented as next actions.
>
> The sections themselves are kept rather than deleted: the analysis of *why* each was exploitable
> is the part worth re-reading before a SaaS pivot re-opens the same surface.

## Posture

**The application layer is sound. The perimeter was not, and the worst of it is now closed.**

No SQL injection anywhere, no dangerous execution primitives, every model covered by an ACL, and
a formula evaluator that genuinely blocks arbitrary code execution with a test proving it. Those
are real strengths and they were verified individually rather than sampled.

The exposure is concentrated in configuration and in the request-routing layer. Until 2026-08-22
one of those findings was a **live one-request cluster takeover**; it is now closed, and what
remains in that layer is the multi-tenant set, which becomes live the moment a second tenant does.

## ~~The one to fix today~~ — SAAS-2, **RESOLVED 2026-08-22**

`/web/database/create` is `auth="none"`, `csrf=False`, and begins:

```python
insecure = odoo.tools.config.verify_admin_password('admin')
if insecure and master_pwd:
    dispatch_rpc('db', 'change_admin_password', ["admin", master_pwd])
```

The same block appears on `duplicate`, `drop`, `backup` and `restore`.

**At audit time `verify_admin_password('admin')` returned `True` on this instance** — verified by
execution, not inferred. The branch was armed: one unauthenticated POST would set the **cluster**
master password to an attacker's value, and that password then authorises backup — a full
`pg_dump` plus filestore zip — of every database. No rate limit, no lockout, no CSRF, no audit
trail beyond a log line. `crypt_context` registers a `plaintext` scheme, so the shipped value
verified as-is.

Only `http_interface = 127.0.0.1` prevented it, and **SaaS is precisely what removes that**.

> **RESOLVED 2026-08-22.** The master password was rotated to a 32-character random value and is
> now stored as a `pbkdf2_sha512` hash, so `verify_admin_password('admin')` returns **False** and
> the branch above is unreachable. `list_db = False` was set in the same change (**OPS-2**).
>
> Two things this did **not** do, and both still matter:
>
> * The branch still exists in core and re-arms instantly if anyone ever sets the master password
>   back to `admin`. It is a configuration guarantee, not a code fix.
> * `/web/database/manager` still renders publicly even with `list_db = False` (**SAAS-10**,
>   still open). Blocking `/web/database/` at the reverse proxy remains the durable control, and
>   the nginx rule now ships in `deploy/README.md` — but nothing enforces that it is deployed.

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
| ~~**SEC-1**~~ **RESOLVED 2026-08-22** | The live master and database passwords were committed to a tracked document (`RECONNAISSANCE.md:232,236,480`, commit `e4ff7dab`) — the actual values, not placeholders. The document flagged them as critical while being the vehicle that published them. **Both rotated; the document redacted.** History was deliberately **not** rewritten: the leaked values were the product defaults `admin` and `odoo`, worthless once rotated. That decision is cheap to revisit only until the first push to a remote (**SUP-2**), after which it becomes expensive |
| ~~**SAAS-2 / OPS-2**~~ **RESOLVED 2026-08-22** | One master password for the whole cluster, the product default, with `list_db = True`. Now a 32-character random value stored hashed, and `list_db = False` |
| **DAT-1** | `odoo.conf`, two full database dumps, the filestore and 75 live session files sit in corporate OneDrive sync |

**Rotation was unavoidable** — the values are in immutable history, so deleting the file did not
undo it. Rotation is what reduced the risk, and it was done on 2026-08-22. **History rewriting
remains an open decision** (see §1 of the remaining-work inventory): it is cheapest **before** the
first push (**SUP-2**) and awkward afterwards, so it is one of the few items with a closing
window.

**Working correctly:** `odoo.conf` was never committed (`.gitignore:38` verified effective). Both
templates use placeholders. No API keys, tokens or private keys anywhere in scope.

## Authorization

**SEC-2 (P1) — no record rules on any local model. RESOLVED 2026-08-23.** Ten global `ir.rule`
records now cover every locally written company-owned model, across the three modules that define
one. Verified by negative control rather than inspection: with the rules disabled, a company A
accounting manager could read company B's VAT return form, boxes, filed return, individual figures
and TDS certificates; with them active, every read is refused.

Two of the ten models — `l10n_np.vat.return.box` and `.line` — had no `company_id` at all, so the
prescribed fix could not have been applied to them as written; each now carries a stored `related`
one. The `('company_id', '=', False)` branch of the suggested domain was deliberately dropped,
since the field is `required=True` everywhere and that branch would only serve to expose a
hypothetical unowned filed return to every company. Full account in `BACKLOG.md`.

**SEC-6 (P2) — the read-only accounting role can rewrite a filed VAT return. RESOLVED
2026-08-23**, and it was *not* the "one-character fix" described below. That single row was also
what granted every **higher** accounting group its access, because they all imply read-only — so
setting it to `1,0,0,0` alone would have stopped `action_compute` working, since computing a
return unlinks and recreates its lines. The readonly row is now `1,0,0,0` and the billing and
manager roles have rows of their own. Six tests, including one asserting the read-only role can
still *read* a line, which is what stops the fix becoming "delete the row".

A related hole surfaced while fixing it: `action_compute` checked no state, so a **filed** return
could be recomputed in place and its filed figures would change with no trace. Now refused until
the return is reset to draft.

The original finding, for context:
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
down. Privileged-user DoS, not anonymous.

> **RESOLVED 2026-08-23**, and *not* by the "one-character fix" this section proposed. Banning
> `**` textually would have left the same class of hole one regex slip away — **a character class
> cannot express "one star but not two"**, which is exactly why `[0-9eE+\-*/(). ]*` admitted it.
> The evaluator no longer calls `eval` at all: the substituted expression is parsed with `ast` and
> walked, and `ast.Pow` is simply absent from the permitted node types, so exponentiation is
> rejected structurally. Thirteen tests, including one that asserts the *refusal* of `9**9**9`
> rather than evaluating it — a test that hangs the runner to prove a hang was fixed is a test
> nobody can run.
>
> A second defect fell out of the rewrite: sequential `str.replace` of box codes could rewrite
> digits inside a float it had already substituted. Substitution is now a single pass with
> boundaries.

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
| ~~SAAS-2 / OPS-2~~ **RESOLVED 2026-08-22** | Default master password + `list_db = True`. Now hashed random, and `list_db = False` |
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

Renumbered 2026-08-23. Struck items are done; the numbering below is what is actually left.

- ~~**SAAS-2 + OPS-2** — strong master password, `list_db = False`.~~ **Done 2026-08-22.** The
  third part of that line, *block `/web/database/*` at the edge*, is **still open** as **SAAS-10**
  and is now the only durable control on that surface.
- ~~**SEC-1** — rotate both credentials.~~ **Done 2026-08-22.**
- ~~**SEC-2** — record rules, before a second company or tenant exists.~~ **Done 2026-08-23**,
  and it did land before a second company — which is why it was cheap.
- ~~**SEC-6**, **SEC-3**~~ **Done 2026-08-23.** **SEC-7** remains.

1. **DAT-1** — client data and credentials out of cloud sync. Needs a hosting decision.
2. **PG-1, PG-2, PG-4** — the revokes, baked into provisioning **before a second database role
   exists**. All XS/S, and PG-1 is a one-line `REVOKE`.
3. **SEC-7** — `os.path.commonpath` containment check on `--modules`. Two lines.
4. **SAAS-10** — block `/web/database/` at the reverse proxy. The nginx rule ships in
   `deploy/README.md`; nothing verifies it is deployed.
5. **SAAS-1 + SAAS-4 + SAAS-11** — anchored `dbfilter`. **Multi-tenant only**, and **SAAS-1 must
   land in the same change as any `db_name` removal**.
6. **SAAS-3** — pin `X-Forwarded-Host` in nginx. Multi-tenant only.
7. **OPS-3, OPS-4** — systemd hardening and the watchdog, once the writable-`/opt` question is
   decided.
8. **SEC-4, SEC-5, SEC-8, SEC-9** — vendored OCA; override locally or report upstream. **Do not
   edit in place** — that destroys the zero-drift property protecting LIC-1.
