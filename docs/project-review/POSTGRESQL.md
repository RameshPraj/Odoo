# PostgreSQL

Findings by ID in [`BACKLOG.md`](BACKLOG.md). Absorbs the schema portion of the earlier
`DATA_AND_INTEGRATIONS.md`.

## Cluster as observed

PostgreSQL **17.10** on `localhost:5433`.

| Role | Superuser | CreateDB | CreateRole | BypassRLS |
|---|---|---|---|---|
| `odoo` | **No** | **Yes** | No | No |
| `postgres` | Yes | Yes | Yes | Yes |

**This is the correct posture.** `CREATEDB` is exactly what `_create_empty_database` needs
(`odoo/service/db.py:143-148`); `SUPERUSER` is not required and must never be granted.
`check_postgres_user()` (`odoo/cli/server.py:36-43`) hard-aborts if `db_user` is `postgres`, and
the project respects that — a dedicated role was created rather than working around it.

| Database | Owner | Size | `odoo` may CONNECT |
|---|---|---|---|
| `odoo19` | `odoo` | 94 MB | yes |
| `postgres` | `postgres` | 8 MB | yes |
| **`ist_datahub`** | `postgres` | **12 GB** | **yes** |

## PG-1 (P2) — the Odoo account can reach an unrelated corporate database

`ist_datahub` is a 12 GB third-party database on the same cluster, and the `odoo` service account
**can connect to it**. I probed precisely what that permits — privilege checks only, no data read:

| Probe | Result |
|---|---|
| CONNECT as `odoo` | **succeeded** |
| Schemas visible | 3 |
| User tables present | 52 |
| **Tables `odoo` can SELECT from** | **0** |
| CREATE in database | no |
| CREATE / USAGE on `public` schema | no / yes |

**So the exposure is metadata, not data.** The Odoo account can enumerate 52 table names and the
schema layout of an unrelated corporate system, and cannot read a single row. Rated **P2**
accordingly, not P0 — the first instinct on seeing a shared cluster is to over-rate this, and the
evidence does not support that.

What it *does* mean: the blast radius of an Odoo compromise (SAAS-2 makes that a one-request
proposition once exposed) includes an authenticated connection to an unrelated production
database. **Fix (XS):** `REVOKE CONNECT ON DATABASE ist_datahub FROM PUBLIC;`

**Separately worth deciding:** whether an accounting SaaS should share a cluster with an unrelated
12 GB corporate workload at all. That is a noisy-neighbour and blast-radius question as much as a
privilege one.

## PG-2 (P2) — new databases default to PUBLIC CONNECT

Every database shows `datacl = NULL`, meaning PostgreSQL's default applies: `CONNECT` is granted
to `PUBLIC`.

Harmless *today*, because only one login role exists and it owns everything. It becomes real the
moment a second login role appears — a per-tenant reporting user, a BI connector, a metrics
exporter, a backup role. That role would be able to connect to **every** tenant database.

**Fix:** make `REVOKE CONNECT ON DATABASE <db> FROM PUBLIC;` part of provisioning, re-granting to
`odoo` explicitly.

## PG-4 (P2) — Odoo re-opens the `public` schema on every database it creates

`odoo/service/db.py:168-174`:

```python
cr.execute("GRANT CREATE ON SCHEMA PUBLIC TO PUBLIC")   # "restore legacy behaviour on pg15+"
```

This deliberately undoes PostgreSQL 15's default hardening, on **every tenant database Odoo
creates**. Combined with PG-2, any additional login role could both connect to and create objects
in every tenant's `public` schema.

**Fix:** `REVOKE CREATE ON SCHEMA public FROM PUBLIC;` in provisioning. The `GRANT` is wrapped in
a try/except that only logs a warning, so revoking afterwards is safe.

## PG-3 (P2) — shared catalogs are cluster-wide

From inside a single tenant's connection: `pg_database` enumerates all databases, `pg_roles` lists
17 roles, and `pg_stat_activity` shows sessions belonging to other databases. Tenant enumeration
is therefore inherent to a shared cluster, and `pg_stat_activity` can expose other tenants' query
text.

Mitigations are partial: restrict `pg_stat_statements`, consider `pg_stat_activity` visibility
limits, or accept enumeration as a known property of shared-cluster tenancy and rely on the
connect/read controls above.

## Cross-database reads — the reassuring part

**A connection to database A cannot read database B**, same role or not. PostgreSQL binds a
backend to one database for its lifetime; there are no cross-database queries. Same-role ownership
does not change this.

Two caveats that must be preserved:

1. **`dblink` / `postgres_fdw` would break it.** Creating either needs superuser, which `odoo`
   lacks. `_create_empty_database` does install `pg_trgm` and optionally `unaccent`
   (`db.py:154-156`) — both harmless. **Never grant `odoo` superuser, and never pre-create
   `dblink` in a template database**, or every tenant inherits a cross-tenant read primitive.
   `db_template` defaults to `template0`, which is clean; a custom template is a fleet-wide
   supply-chain risk.
2. **`db_user` is the isolation boundary for the entire fleet.** `CREATEDB` implies every tenant
   database is owned by the same role, which is what `list_dbs`'s ownership filter relies on
   (`db.py:449`) — a useful property, since a second cluster on a different role is invisible. But
   compromise of `db_password` is full-fleet compromise. The Linux template's peer-authentication
   approach (`db_host = False`, no password at all) is materially better than the password in the
   dev config.

## Schema of the custom models

| Table | Rows | Indexes |
|---|---|---|
| `l10n_np_loan` | 0 | pkey |
| `l10n_np_loan_line` | 0 | pkey, `loan_id`, `date` |
| `l10n_np_tds_category` | 0 | pkey |
| `l10n_np_tds_certificate` | 0 | pkey |
| `l10n_np_vat_return` | 0 | pkey |
| `l10n_np_vat_return_line` | 0 | pkey |
| `l10n_np_vat_return_form` | 0 | pkey |
| `l10n_np_vat_return_box` | 0 | pkey |

**SCH-2 — every custom table is empty**, and the whole database holds 3 posted journal entries.
Nothing has been exercised at any realistic volume, so **no performance claim about this suite is
evidence-based**. That is expected for modules that deliberately ship with empty rate and form
tables — but the first real month of data will also be the first real test.

**SCH-1 — business foreign keys are unindexed**: `vat_return_line.return_id`, `.box_id`,
`loan.partner_id`, and `company_id` throughout. `loan_line.loan_id` and `.date` *are* indexed, so
the pattern was understood and applied inconsistently. Low impact at present volume;
`company_id` becomes hot the moment SEC-2 adds record rules, because every query then filters on
it. (`create_uid`/`write_uid` being unindexed is normal in Odoo and not worth changing.)

## Transactions, locking and concurrency — verified safe

Odoo runs **REPEATABLE READ** (`odoo/sql_db.py:373`) and retries serialization failures up to five
times (`odoo/service/model.py:29-30`).

The money-posting paths in `l10n_np_loan` guard idempotency with an in-memory
`line.state == 'posted'` check and take **no row locks**. That is correct and not a defect: two
concurrent posts both UPDATE the same row, the second loses on serialization, is retried,
re-reads `posted`, and raises. Checked rather than assumed.

One genuine subtlety the code already handles: writes to `res.company` flush through
`cr.precommit` and can outlive `cr.rollback()`. The lock-dates and BS-date suites create throwaway
companies specifically to avoid corrupting the real one, with comments explaining why. **TST-7**
is the open question of whether those throwaways accumulate.

## Connection management

See **SAAS-8** in [`SAAS_MULTI_TENANCY.md`](SAAS_MULTI_TENANCY.md) for the full arithmetic. The
essential point: `db_maxconn` is a **global per-process** pool, not per database
(`sql_db.py:816-832`), and connections are reusable only on a matching DSN. With `workers = 5`,
worst case ≈ 513 backends against PostgreSQL's default `max_connections = 100` — **PostgreSQL
exhausts first**, and a pooler is required well before 100 tenants.

## Backup, restore and lifecycle

**There is no backup.** Three things resemble one and are not:

| Apparent backup | Why it is not |
|---|---|
| OneDrive sync (DAT-1) | Not a git remote; also the leading corruption risk, and would replicate damage |
| Synced `.odoo_data/filestore` | Only meaningful paired with a `pg_dump` taken at the same instant; a drifting copy matches no dump |
| The two `.dump` files | Development milestones (`before_oca`, `before_phase1`), not a schedule |

A working arrangement needs three artefacts taken together and **rehearsed**: a `pg_dump` of the
tenant database, its filestore at the same instant, and its configuration. Restore currently also
requires the manual `nepali-datetime` install (DEP-1) and, after any Odoo upgrade, re-running
`l10n_ne/apply.py` (SUP-3). An untested restore is a hypothesis.

For multi-tenant, backup must be **per tenant** and restorable **per tenant** — `/web/database/backup`
exists but is gated by the cluster master password (SAAS-2), which is not an acceptable
control for routine operations.

## Recommended sequence

1. **PG-1** — revoke PUBLIC CONNECT on `ist_datahub`. **XS**
2. **PG-2 / PG-4** — bake both REVOKEs into provisioning before any second role exists. **S**
3. **SCH-1** — index the business FKs, alongside SEC-2's record rules. **XS**
4. Backup/restore **rehearsal**, per tenant. **M**
5. **SAAS-8** — PgBouncer before crossing ~50 tenants. **L**
6. **SCH-2** — load representative data and re-measure. **M**
