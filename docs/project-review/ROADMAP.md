# Roadmap

Five phases, as specified. Each has an exit criterion; do not start the next until it is met.
Tickets in [`JIRA_BACKLOG.md`](JIRA_BACKLOG.md), findings in [`BACKLOG.md`](BACKLOG.md).

Effort excludes the two decisions that need other people: SPIKE-2 (legal) and the SME sign-off
register.

---

## Phase 1 — P0/P1 Safety
*Security, accounting correctness, tenant isolation, data-loss. Nothing here is optional.*

| # | Ticket | What | Effort |
|---|---|---|---|
| 1 | **BUG-1** | Strong `admin_passwd`; `list_db = False`; block `/web/database/*` at the edge | XS |
| 2 | **BUG-13** | Correct `addons_path`/`data_dir`; reconcile the two filestores | S + M |
| 3 | **TASK-3** | Create a remote and push | XS |
| 4 | **TASK-2** | Rotate both credentials | S |
| 5 | **BUG-14** | Client data and credentials out of cloud sync; relocate the dumps | S–M |
| 6 | **BUG-6** | Rename the report models so the statements render | S |
| 7 | **BUG-8** → **BUG-7** | Fix the guarding test, *then* backfill the tax tags | S + M |
| 8 | **BUG-10**, **BUG-11**, **BUG-9** | Export tax substitution; unallocated earnings; loan currency | XS–M |
| 9 | **TASK-4** | PostgreSQL revokes | S |

**Why this order.** BUG-1 first: it is XS effort against a live one-request cluster takeover, and
everything else is moot if the master password is claimable. BUG-13 next because attachments are
being written to the wrong place *now* — every day it waits, reconciliation gets harder. TASK-3
before BUG-14 so a second copy exists before anything moves.

**BUG-8 strictly before BUG-7.** Fix the test that hides the defect first, watch it fail, then fix
the defect. That ordering is the entire lesson of this pair, and it applies again at BUG-6 (add
the render assertion in the same change).

**Decided 2026-08-27: no history rewrite is needed.** This item asked whether to purge committed
credentials before the first push. Checked rather than assumed, and the premise was false:

* `odoo.conf` was **never committed** — `git log --all -- odoo.conf` is empty. It has been
  gitignored from the baseline commit onward.
* `odoo.conf.example` *is* committed and carries `admin_passwd` and `db_password`, but every value
  across all four commits touching it is a **9-character placeholder**, not a real secret.
* The Enterprise password pasted into a chat session on 2026-08-27 appears in **zero** commits.

So there is nothing to purge, and `git filter-repo` — irreversible, and guaranteed to invalidate
every existing clone — must **not** be run for this. Recorded with the evidence so the question is
not reopened as a precaution later. The one-time-window framing was wrong.

**Exit criteria**
- `verify_admin_password('admin')` is False; `/web/database/*` unreachable externally
- Every referenced attachment resolves; no writes to the `Downloads` tree
- History present on a remote; `git fsck` clean
- No dump, filestore, session file or `odoo.conf` inside the sync root
- All three statements render HTTP 200; a posted invoice produces non-zero VAT boxes tying to the
  ledger, proven by a test that **cannot skip**

---

## Phase 2 — Stabilization
*Bugs, tests and reliability. Make the suite trustworthy before building on it.*

**Depends on** Phase 1 (a remote is needed for CI; paths must be stable).

| # | Ticket | What | Effort |
|---|---|---|---|
| 1 | **BUG-18** | Declare and pin `nepali-datetime`, `polib`, `websocket-client` | XS |
| 2 | **STORY-1** | One command runs all eight suites, **reporting skip counts** | M |
| 3 | **BUG-12** | Test the TDS certificate path; remove the silent `getattr` defaults | S |
| 4 | **TASK-8** | Wire `selftest.py` into the suite | S |
| 5 | **STORY-4** | Fixtures instead of live database state | M |
| 6 | **TASK-10** | Shared `lxml` well-formedness mixin across all eight modules | S |
| 7 | **BUG-21** | Wrap `month_length()`; bound-check the fiscal-year wizard | XS |
| 8 | **TASK-11** | Precision-safe monetary assertions | S |
| 9 | **TASK-9** | JavaScript test suite | M |

**Why this order.** BUG-18 first — without it nothing installs on a clean machine, so no CI is
possible at all. STORY-1 next so the remaining fixes are visible when they land. TASK-8 is
disproportionately valuable: the verification already exists and works; it just needs calling.

**Exit criteria**
- A fresh venv from the requirements files installs all 15 modules
- One command runs the whole custom suite, reports skips, and exits non-zero on failure. **Met as of
  2026-08-19**: `run-odoo.ps1 test` / `run-odoo.sh test` runs **326 tests** across 17 modules — not
  the 121 this criterion originally named — and exits 0. It was unmeetable until TST-8 was fixed,
  because 15 `date_range` errors guaranteed a non-zero exit regardless of the code under test. What
  remains of this criterion is the *skip* reporting (**TST-3**), which is still not done.
- Every suite passes on both an empty and a fully configured database
- The 46,022-day BS cross-check runs in CI

---

## Phase 3 — SaaS Foundation
*Tenant provisioning, routing, isolation, backups and lifecycle.*

**Depends on** Phase 2 — do not build tenancy on an unverified suite.

| # | Ticket | What | Effort |
|---|---|---|---|
| 1 | **STORY-5** | The nine cross-tenant isolation tests — **written first, before the pivot** | L |
| 2 | **BUG-2** | Anchored `dbfilter`; `X-Odoo-Database` and `?db=` refuse non-matching databases | S |
| 3 | **BUG-3** | nginx pins `X-Forwarded-Host` | XS |
| 4 | **BUG-15** | Record rules on all ten company-scoped models | S |
| 5 | **BUG-4** | Cron allowlist — **in the same change as any `db_name` removal** | M |
| 6 | **BUG-5** | Cross-tenant session destruction: per-tenant session dirs, or separate instances | M |
| 7 | — | Scripted provisioning: fresh `database.secret`, both PG revokes, per-tenant `ir.mail_server`, routing registration | L |
| 8 | — | Scripted offboarding: drop database, remove filestore, **purge sessions**, revoke DNS/certs | M |
| 9 | — | Per-tenant backup **and rehearsed restore**, producing a fresh `database.secret` | M |

**Why this order.** STORY-5 first is deliberate: the isolation tests are the only way to know the
pivot is safe, and writing them afterwards means shipping on hope. BUG-15 sits here rather than
Phase 1 because it is latent while single-company — but it must land **before** the second tenant,
not after.

**The critical constraint:** `db_name = odoo19` currently constrains routing, `list_dbs` **and**
cron simultaneously. Removing it opens all three at once. BUG-2 and BUG-4 must land in the same
change as its removal.

**Exit criteria**
- All nine isolation tests pass against two real tenant databases
- A tenant can be provisioned, suspended and offboarded by script, with no residue
- A per-tenant restore has been rehearsed and produces a fresh `database.secret`
- A suspended tenant executes no crons and sends no mail

---

## Phase 4 — Hardening
*Security, observability and CI/CD.*

| # | Ticket | What | Effort |
|---|---|---|---|
| 1 | **STORY-2** | CI on push, with ruff and `pylint-odoo` configured | M |
| 2 | **BUG-19** | Core-group changes survive `-u account`, asserted by a test | S |
| 3 | **TASK-6** | Version bumps and migration scaffolding | S |
| 4 | **BUG-16**, **BUG-17**, **TASK-5** | ACL fix, `**` ban, local overrides for vendored OCA | S |
| 5 | **TASK-15** | Upgrade runbook + `i18n_extra` health check | M |
| 6 | **OPS-3**, **OPS-4** | systemd hardening; watchdog restored | S |
| 7 | — | Observability: health check, `data_dir` assertion, `i18n_extra` count, non-zero-VAT check, rendered-statement check, per-tenant request/error rate | M |
| 8 | **TASK-1** | Database-manager surface blocked and verified | XS |
| 9 | **TASK-13**, **TASK-12** | Project README, document dating, corrected `VENDORED.md` | S |

**Why observability is here and not earlier:** five of this system's failure modes are **silent** —
translations reverting, VAT reporting nil, reports raising for users but not tests, attachments
written to the wrong store, and routing anomalies. Monitoring should be built for exactly those,
which means knowing what they are first.

**Exit criteria**
- CI green on push including lint; a changed module with an unchanged version is flagged
- An upgrade rehearsal on a scratch copy leaves translations intact
- Alerts exist for all five silent failure modes

---

## Phase 5 — Scale and Upgradeability
*Performance, maintainability and Odoo upgrade readiness.*

| # | Ticket | What | Effort |
|---|---|---|---|
| 1 | **TASK-12** → **SPIKE-2** | Correct the facts, then decide the AGPL position | S |
| 2 | **TASK-16** | Vendored OCA provenance as SHAs | S |
| 3 | **SAAS-8** | PgBouncer (session mode) — **before ~50 tenants** | L |
| 4 | **SAAS-7** | Cron sharding or an external scheduler — before ~200 tenants | L |
| 5 | ~~**SCH-1**~~, **SCH-2** | ~~Index business FKs~~ **done 2026-08-23**, immediately after SEC-2 put `company_id` in the WHERE clause of every query on those tables. **SCH-2** — load representative data and re-measure — remains | M |
| 6 | **STORY-3** | BS-aware period filters and group-by | L |
| 7 | **CI-2** | Containerise so dev and prod share an artefact | M |
| 8 | **SPIKE-1** → implementation | How Odoo core is obtained | M → XL |
| 9 | **TASK-14**, cleanup | Rename `l10n_ne/`, empty directories, duplication | S |

**Why SPIKE-1 is last.** It is the largest change available and the wrong choice is expensive to
undo. It also subsumes SUP-3, so deciding it early would waste TASK-15.

**STORY-3 deserves emphasis:** it is the item that decides whether this is a Nepali accounting
system or a Gregorian one with Nepali date labels. Everything else about the BS work is already
correct; this is where it currently stops.

**Exit criteria**
- Connection and cron behaviour measured at the target tenant count, not assumed
- Manifests state a licence consistent with the decided position
- A demonstrated path to applying an Odoo security release

---

## Dependency graph

```
Phase 1 ─ BUG-1 ─────────────────────────────────────────┐
          BUG-13 ──► TASK-4                              │
          TASK-3 ──► BUG-14                              │
          BUG-8 ──► BUG-7                                │
          BUG-6, BUG-9, BUG-10, BUG-11                   ▼
Phase 2                                    (remote + stable paths)
          BUG-18 ──► STORY-1 ──► STORY-4, TASK-8, TASK-9
                              └► BUG-12, TASK-10, TASK-11
                                                          ▼
Phase 3                                          (verified suite)
          STORY-5 ──► BUG-2 ─┬─► BUG-4        ← same change as db_name removal
                     BUG-3   │
                     BUG-15  └─► provisioning / offboarding / backup
                                                          ▼
Phase 4                                        (tenancy proven)
          STORY-2 ──► BUG-19, TASK-6
          TASK-15, OPS-3/4, observability
                                                          ▼
Phase 5   TASK-12 ──► SPIKE-2
          SAAS-8, SAAS-7, STORY-3, CI-2
          SPIKE-1 ──► implementation  (subsumes SUP-3 / TASK-15)
```

---

## Go-live

**Single-tenant:** earliest after **Phase 2**, with the SME sign-off register closed. Phase 1
clears the blockers; Phase 2 makes the result trustworthy.

**Multi-tenant SaaS:** not before **Phase 3 exits**, with all nine isolation tests passing against
real tenant databases and provisioning/offboarding scripted. The AGPL decision (SPIKE-2) should
also land before onboarding a third-party tenant, since network provision is precisely what
engages §13.

Phase 5 is not a go-live prerequisite — but the longer it waits, the longer you are running an
Odoo you cannot patch.
