# SaaS and Multi-Tenancy

Findings by ID in [`BACKLOG.md`](BACKLOG.md).

> **Scope note, updated 2026-08-31.** This began as a design review with **no tenant code in the
> repository at all**. That is no longer true of the lifecycle: `tools/provision_tenant.py`,
> `tools/offboard_tenant.py`, `tools/check_tenant_isolation.py` and the shared
> `tools/tenant_boundary.py` now exist and are exercised against real databases — see
> **[The provisioning spine](#the-provisioning-spine-built-2026-08-31)** below.
>
> **Routing still does not exist**, and that is deliberate: `dbfilter`, `proxy_mode` and the
> nginx layer are the next step, and they are what make the HTTP-level isolation tests runnable.
> Everything in the gap analysis upstream of database resolution therefore still stands. Every
> claim below cites upstream Odoo source.

## The one-sentence summary

**Odoo's tenant boundary is the database name resolved per request.** Everything *downstream* of
that resolution — ORM, filestore, users, session tokens — is correctly per-tenant and, in the
case of session tokens, cryptographically bound. Everything *upstream* of it — Host parsing,
`dbfilter`, the `X-Odoo-Database` header, `?db=`, the master password, the session store, the
cron enumerator, the connection pool — is **process-global and shared by every tenant.** All
seven P0s live in that upstream layer.

## What the substrate gets right

Do not break these. They are the reason SAAS-1 is a *reachability* finding rather than a
data-read one.

| Mechanism | Evidence | Why it matters |
|---|---|---|
| **Per-database filestore** | `config.filestore(dbname)` = `data_dir/filestore/<db>` (`odoo/tools/config.py:1031`); `_full_path` strips `.` and `:` before joining (`ir_attachment.py:124-129`) | No path traversal out of a tenant's directory; create/drop/rename/duplicate all move it correctly |
| **Per-database identity** | `res.users`, groups and API keys are ordinary per-DB records; auth resolves on a cursor bound to one database (`odoo/http.py:1249`) | No global user table, no shared credential store — and none to leak |
| **Session tokens HMAC'd with a per-database secret** | `res_users.py:832-849, 871-884` — the HMAC key includes `ir_config_parameter['database.secret']`, regenerated per database (`db.py:203,374`) | **The strongest primitive in the stack.** A session minted in tenant A cannot validate in tenant B even at the same `uid` |
| **Session/DB rebinding with forced logout** | `odoo/http.py:1829, 1844-1848` — if the resolved database differs from `session.db`, `logout(keep_db=False)` | Correct — but a no-op when `dbfilter` is unset (SAAS-1) |
| **`list_dbs` scoped to role ownership** | `db.py:449` — `datdba = current_user` | A second Odoo cluster on a different PostgreSQL role is invisible to this one |
| **`odoo` role is not superuser** | verified on the live cluster: `rolsuper=False`, `rolcreatedb=True` | Correct minimum. `check_postgres_user()` (`cli/server.py:36-43`) hard-aborts on `postgres` |

**One residual on session tokens (NEEDS_VERIFICATION against whatever you build):** if
provisioning ever clones a template with `CREATE DATABASE … TEMPLATE` *outside*
`exp_duplicate_database`, `database.secret` is copied verbatim and this primitive collapses — a
session for tenant A would then authenticate as the same `uid` in tenant B. Always provision
through Odoo's own duplicate/restore path, or regenerate `database.secret` explicitly.

## Isolation boundaries, layer by layer

| Layer | Isolated? | Evidence |
|---|---|---|
| PostgreSQL data | **Yes** — no cross-database queries exist | verified; and `dblink`/`postgres_fdw` need superuser, which `odoo` lacks |
| Filestore / attachments | **Yes** | `config.py:1031` |
| Users, groups, API keys | **Yes** | per-DB tables |
| Session **validity** | **Yes** (cryptographic) | `res_users.py:871-884` |
| Session **files** | **No — shared directory** | SAAS-5: `config.py:1019-1029` has no dbname component |
| Request routing | **Config-dependent** | SAAS-1, SAAS-3, SAAS-4 |
| Master password | **No — one cluster-wide secret** | SAAS-2 |
| Cron execution | **No — all role-owned databases** | SAAS-7 |
| Connection pool | **No — global per process** | SAAS-8 |
| Outbound mail | **Config-dependent** | SAAS-9 |
| Logging | **Partial** | SAAS-15: `dbname` is `?` on the nodb path |
| Asset bundle cache | **Content-addressed, with a bypass** | SAAS-13 |

## The seven P0s in dependency order

1. **SAAS-2** — a live one-request cluster takeover. `verify_admin_password('admin')` returns
   `True` on this instance, so the auto-set branch at `database.py:71-75` is armed. Fix first; it
   is XS effort and currently gated only by a localhost bind that SaaS removes.
2. **SAAS-6 / SAAS-1** — `list_db = True` with `dbfilter` unset. Together these expose the
   database manager and let a client select any tenant with an `X-Odoo-Database` header.
3. **SAAS-3** — `proxy_mode` makes `X-Forwarded-Host` authoritative for tenant routing, and the
   documented nginx does not pin it.
4. **SAAS-4** — `authenticate(db=…)` and `?db=` are gated only by `db_filter`, so that regex is
   the whole boundary.
5. **SAAS-5** — the shared session directory permits cross-tenant session destruction.

Note the shape: **four of the five are configuration**, fixable in under a day. SAAS-5 is an
upstream design property that needs an architectural answer.

## Scale thresholds — where each mechanism breaks

You have not fixed a target tenant count, so here are the numbers rather than a recommendation.
All figures are per Odoo **process** unless stated.

### Connection pool (SAAS-8)

`_Pool` is a module-level singleton sized `int(db_maxconn)` (`sql_db.py:816-832`), and a
connection is reusable only when the DSN — including database name — matches (`:664-665`). At
cap it evicts an idle connection of **any** database or raises `PoolError` (`:679-690`).

| Tenants | Behaviour with `db_maxconn = 64` |
|---|---|
| ≤ 50 | Comfortable. Most tenants keep a warm connection. |
| ~100 | **The pool breaks before PostgreSQL does.** 64 slots against 100 distinct DSNs means constant evict-and-reconnect thrash on nearly every request. Latency degrades before anything errors; a burst across >64 distinct tenants surfaces as HTTP 500. |
| ~1000 | Not viable without a pooler. |

In prefork with `workers = 5`, each HTTP worker, the gevent worker, both cron workers and the
master own an **independent** pool: worst case ≈ (5 + 1 + 2) × 64 + master ≈ **513 backends**
against PostgreSQL's default `max_connections = 100`. **PostgreSQL exhausts first.**

Also note: without a configured replica, the readonly path collapses onto the same pool
(`registry.py:1190-1212`), and `_serve_db` opens a readonly cursor for *every* request
(`http.py:2276`).

### Registry cache

`Registry.registries` is an LRU sized `limit_memory_soft // 15 MiB` on POSIX
(`server.py:1555-1568`). With `limit_memory_soft = 2 GiB` that is ~136 registries per worker at
roughly 10 MB each ≈ **1.4 GB of registries alone**, against `limit_memory_hard = 2.5 GB`. Below
the LRU size you get thrashing rebuilds — a full module-graph load per eviction, seconds each.

### Cron fan-out (SAAS-7)

Every 60 s (`SLEEP_INTERVAL`, `server.py:68`) each cron thread re-lists all databases and loops
`_process_jobs` over **all of them** (`server.py:581-605`). Per database per sweep: a connect, a
cursor, and ~3 queries minimum even when idle.

| Tenants | Idle cost per cron worker |
|---|---|
| 100 | ~300 queries/min + 100 connection setups/min. Tolerable. |
| 1000 | ~3000 queries/min + 1000 setups/min; the 60 s budget is **60 ms per database**, which a single cold registry load blows. One slow tenant stalls the queue behind it. |

In prefork, `WorkerCron` calls `sql_db.close_db()` after each database when `db_count > 1`
(`server.py:1467-1469`), so **every tenant sweep is a fresh TCP + auth handshake** — no pooling
benefit at all.

**Conclusion: Odoo's cron design does not scale past low hundreds of databases per instance.**
Sharding tenants across instances is not an optimisation, it is the mechanism.

### Practical bands

| Band | Viable shape |
|---|---|
| **≤ 50 tenants** | One instance, database-per-tenant. Anchored `dbfilter`, semi-manual provisioning. Everything in this document is configuration work. |
| **50–500** | Needs PgBouncer (session mode), cron sharding or an external scheduler, and automated provisioning. Registry LRU and memory become the sizing constraint. |
| **500+** | Single-instance database-per-tenant stops working. Needs a routing tier, instance shards with a tenant→shard map, per-shard cron, and orchestration. Materially different architecture. |

## Recommended target architecture

Deliberately minimal, because you have not fixed scale or instance model.

```
            ┌──────────────────────────────────────────────┐
  client ──►│ nginx / edge                                 │
            │  · terminates TLS, one cert per tenant domain│
            │  · MUST pin X-Forwarded-Host  (SAAS-3)       │
            │  · MUST block /web/database/*  (SAAS-2,10)   │
            └───────────────────┬──────────────────────────┘
                                ▼
            ┌──────────────────────────────────────────────┐
            │ Odoo instance (shard)                        │
            │  · dbfilter = ^%d$   anchored   (SAAS-1,11)  │
            │  · list_db = False              (SAAS-6)     │
            │  · strong admin_passwd          (SAAS-2)     │
            │  · no smtp_* in odoo.conf       (SAAS-9)     │
            │  · limit_time_real = 120        (OPS-4)      │
            │  · cron allowlist, not all DBs  (SAAS-7)     │
            └───────────────────┬──────────────────────────┘
                                ▼
                    PgBouncer (session mode)   ← required >50 tenants (SAAS-8)
                                ▼
            ┌──────────────────────────────────────────────┐
            │ PostgreSQL                                   │
            │  · one database per tenant, owned by `odoo`  │
            │  · REVOKE CONNECT FROM PUBLIC   (PG-2)       │
            │  · REVOKE CREATE ON SCHEMA public (PG-4)     │
            │  · never grant superuser; never pre-create   │
            │    dblink/postgres_fdw in a template (PG-5)  │
            └──────────────────────────────────────────────┘
```

**Provisioning must, at minimum:** create the database through Odoo's own path (so
`database.secret` is fresh), revoke the two PUBLIC grants, create a per-tenant `ir.mail_server`
with its own `from_filter` and bounce/catchall aliases, and register the tenant in whatever
routing map the edge uses. **Offboarding must** drop the database, remove the filestore
directory, purge that tenant's sessions from the shared store, revoke the DNS/cert, and retain
backups per your policy — each of which is a place data can be left behind.

## Lifecycle gaps — partly closed 2026-08-31

| Concern | Status |
|---|---|
| Tenant provisioning | **`tools/provision_tenant.py`** (2026-08-31). Notably it does *not* use `exp_create_database`, which is gated by `list_db` — see below |
| Tenant offboarding | **`tools/offboard_tenant.py`** (2026-08-31). Dumps, drops, and purges the filestore *and* the shared session store, which is where the residue this row warned about actually lives |
| Per-tenant backup / restore | **Backup half done** — offboarding dumps via `pg_dump`, deliberately not `/web/database/backup`, which needs the cluster master password (SAAS-2). **Restore is not built**, and is spec test 7 |
| Failed/provisional tenant cleanup | **Done** — provisioning rolls back its own database if a later step fails, so a half-provisioned tenant is not left for someone to find |
| Migrations across tenants | **No code**, and no migration scripts exist at all (UPG-2) |
| Module upgrades across tenants | **No code.** Module versions never change (UPG-2), so version-comparison upgrades skip them entirely |
| Domain/subdomain mapping | **No code.** There is no `res.tenant` model — routing is a regex over `pg_database` and nothing else |
| Noisy-neighbour control | **None.** `limit_time_real = 0` in dev removes even the runaway-request watchdog (OPS-4) |
| Disaster recovery | **None.** No remote (SUP-2), no rehearsed restore |
| Secrets isolation | **None.** One `db_password`, one `admin_passwd`, one fleet |

## The provisioning spine, built 2026-08-31

Four tools. The decision behind them was that provisioning and isolation are **one deliverable**,
not two — `TESTING.md` settles it: *"The suite needs two databases … provisioned the way
production will provision them. Anything less tests a fiction."* The script gives the tests their
fixture; the tests give the script its acceptance criteria.

| Tool | Role |
|---|---|
| `tools/tenant_boundary.py` | The naming boundary, once, for every tool that can destroy data |
| `tools/provision_tenant.py` | create → install → harden → rotate secrets → **verify**, with rollback |
| `tools/check_tenant_isolation.py` | the spec's nine tests, PASS / FAIL / **GAP** |
| `tools/offboard_tenant.py` | dump → drop → purge filestore → purge sessions |

### Two source findings that changed the design

**`list_db = False` blocks every mutating database function.** `db.py:46-53`'s
`check_db_management_enabled` raises `AccessDenied` when `list_db` is falsy, and it decorates
`exp_create_database`, `exp_duplicate_database`, `exp_drop`, `exp_dump`, `exp_restore`,
`exp_rename`, `exp_change_admin_password` and `exp_migrate_databases` — everything that mutates.
So provisioning **cannot** go through the db service, and instead uses `_create_empty_database`
(`db.py:128`, undecorated) plus `Registry.new(install_modules=…)`. That is better than a
workaround: **the database manager never has to be enabled to onboard a tenant**, so
`list_db = False` stays on permanently rather than being toggled during onboarding — which is
precisely when somebody forgets to toggle it back. It also means the SAAS-2 takeover route stays
shut throughout the tenant lifecycle.

**The template-clone trap is real, and one API choice away.** `database.secret` is a
per-database uuid4 (`ir_config_parameter.py:18-25`) and session tokens are minted from it
(`res_users.py:833-844`). Odoo's own `exp_duplicate_database` calls
`ir_config_parameter.init(force=True)` (`db.py:203`, *"force generation of a new dbuuid"*) — but
that path is blocked by `list_db = False`. A hand-rolled `CREATE DATABASE … TEMPLATE …`, which is
the obvious optimisation and far faster than a module install, **copies the secret**, and then a
session minted in tenant A authenticates as the same uid in tenant B. `provision_tenant.py`
rotates unconditionally so it stays correct if it is ever changed to clone, and the check is
asserted rather than assumed.

**That assertion was verified by deliberately breaking it**: alpha's secret was copied onto beta
by hand, and the harness failed with exit 1 and a message naming the likely cause. An assertion
that has never failed is an assertion nobody has tested.

### What the harness covers, and what it does not

Run against two real tenants: **15 pass, 0 fail, 2 known gaps, 3 deferred.**

The three outcomes matter. `TESTING.md` says of spec 9's second half that it *"will fail today
(SAAS-8: one global pool) — which is precisely the point of writing it"*, so a harness with only
pass and fail would have forced that check to be deleted or to lie. **GAP** means asserted, known
broken, tracked as a finding, and not a build failure.

The two gaps it reports are exactly the findings this document predicted:

* **SAAS-7** — cron scope. The harness asserts the coupling explicitly rather than describing it.
* **SAAS-8** — `db_maxconn=64 × 2 processes = 128` against `max_connections=100`, **already
  over-subscribed with one tenant**. PgBouncer belongs with `workers > 0`, not at "~50 tenants".

Deferred, and printed as deferred on every run so the gap is visible rather than buried: the HTTP
halves of specs 1, 2 and 3, all of spec 7, and spec 9's latency half. They need a running server
with `dbfilter` set and two hostnames resolving to it — i.e. the routing layer, which is the next
step. Stubs that passed while asserting nothing would be worse than a recorded blank; that is the
TST-1/TST-3/TST-9 failure mode this project has already been bitten by four times.

### The boundary is structural, not procedural

The cluster is shared with another team's `ist_datahub`, and the primary database is `odoo19`.
Rather than relying on care, `tenant_boundary.assert_tenant` requires the shape
`odoo19_t_<name>` — so **`odoo19` cannot be passed to a destructive tool at all**, and the
configured `db_name` is refused by a second independent gate. Both run before any connection
opens, so a refusal cannot have side effects.

Verified across all three tools × five dangerous names — `odoo19`, `ist_datahub`, `postgres`,
`template1`, `odoo19_probe` — all fifteen refused with exit 1, every database intact.

Offboarding **dumps before it drops and abandons the run if the dump fails**, which it did on
first use: `pg_dump` was not on PATH, so the tool refused to delete anything. It now finds the
newest `pg_dump` under `C:\Program Files\PostgreSQL` (this machine has 10, 13, 16 and 17
installed, none on PATH), preferring the highest version because `pg_dump` refuses to dump a
server newer than itself.

## Identity: the Okta-style portal

The requirement is one login across several company accounts. Two designs, and only one gives a
portal:

| | Design | Portal behaviour |
|---|---|---|
| (a) | One Okta org per Odoo tenant | Clean 1:1, but **no** cross-tenant portal — each org is an island |
| (b) | **One Okta org, one app integration per tenant** | The Okta end-user dashboard *is* the tenant picker: a user sees tiles only for the companies they are assigned |

**(b) is the answer**, and most of it is not built here — Okta already does app assignment,
group entitlement and the dashboard.

The Odoo-side catch: **auth configuration lives inside each database.** There is no cross-database
user directory in Community, so each tenant needs its own `auth_oauth` provider record pointing at
its own Okta app integration. IdP wiring is therefore a **per-tenant provisioning step**, and
`provision_tenant.py` is where the hook belongs. `auth_oauth` (OIDC) ships with Odoo and is
currently uninstalled; SAML needs OCA's `auth_saml`, which is not vendored here.

Stated plainly because it is easy to assume otherwise: **Okta solves authentication and nothing
else.** It does not route requests to the right database — that is `dbfilter`, `proxy_mode` and a
pinned `X-Forwarded-Host` (SAAS-1/3/11), all still open.

## The single riskiest edit in the pivot

`db_name = odoo19` currently appears in all three configs. It is doing three jobs at once:
constraining `db_filter` (`http.py:420-423`), constraining `list_dbs` (`db.py:438-442`), and
constraining **cron** (`server.py:100`).

**Removing it for multi-tenancy simultaneously opens routing (SAAS-1) and cron fan-out
(SAAS-7).** Do not remove it until `dbfilter` is anchored and the cron list is explicitly
scoped. This is the one change most likely to turn a working single-tenant instance into a
leaking multi-tenant one in a single commit.
