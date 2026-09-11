# Executive Summary

**Audit date** 2026-08-14 · **Commit** `962b30b9` · **Read-only throughout — nothing modified.**

Scope: the 632 tracked files this project owns, plus configuration, deployment, tooling, hosting,
the live PostgreSQL cluster, and the Odoo substrate as it bears on multi-tenancy. The 51,775
vendored upstream files were not reviewed as code, but *how they got here and how they get
patched* is in scope and is among the worst findings.

All findings and evidence in [`BACKLOG.md`](BACKLOG.md). **125 findings: 10 P0, 29 P1, 50 P2,
28 P3, 6 P4** (123 table entries; `DEP-3/4/5` is one row covering three).

**Twenty-seven are RESOLVED** as of 2026-08-23 — ACC-2, ACC-3, BS-1, BS-2, BS-4, BS-20, DEP-1,
DOC-3, FIN-1, FIN-2, FIN-3, OPS-1, OPS-2, OPS-7, QA-1, SCH-1, SEC-1, SEC-2, SEC-3, SEC-6, SEC-12,
SAAS-2, TST-1, TST-5, TST-8, TST-9, UPG-1, UPG-2 — leaving **96 entries (98 findings) open**, four
of them partial (CI-1, CI-2, OPS-6, TST-7).

BS-1, BS-2 and BS-4 were **already fixed** and only appeared open because the findings cite paths
that commit `c7a73ae8` moved; see the note under BS-1 in `BACKLOG.md`.

(This count previously read "88 findings", then "124 / 111 open". Both had drifted. P2 gained a
fiftieth row when `TST-9` was appended on 2026-08-23 without re-totalling — the same failure this
note was written to complain about, repeated. **Derive it, do not carry it forward.**)

> This audit supersedes the previous pass and **corrects two of its conclusions**, stated
> explicitly rather than silently amended. See *Corrections* below.

---

## 1. Overall health and production-readiness score

**Health: Amber-Red. Production readiness: 3 / 10. SaaS readiness: 2 / 10.**

The engineering is markedly better than the operations, and better than the test suite implies.
The Python is idiomatic Odoo 19 with no API rot anywhere, no core files modified, no
monkeypatching, uniformly parameterised SQL, and a Bikram Sambat conversion I verified across all
46,022 supported days with zero divergence. Someone who knew what they were doing wrote this.

What surrounds it is not ready. There is a **live one-request cluster takeover**, three of the
four things an accountant would actually use are broken, no CI, no backup, no remote, and no tenant
isolation layer. (A running configuration pointing at deleted directories was fixed on 2026-08-14;
no data was lost.)

The single most important observation: **all four correctness defects are covered by green tests.**
The suite tests mechanism thoroughly and outcomes barely at all.

| Area | Score | Why |
|---|---|---|
| Domain code quality | 8/10 | Idiomatic, well commented, no deprecated API |
| Bikram Sambat mathematics | 10/10 | 46,022 days verified both directions, zero divergence |
| Odoo upgrade safety | 7/10 | No core modification except UPG-1; two seams to watch |
| Statutory correctness | **6/10** | FIN-2, FIN-1's data defect, ACC-2 and ACC-3 closed. Remaining: ACC-1, and the SME-gated IRD box layout |
| Application security | 6/10 | No injection, ACLs complete; no record rules |
| Perimeter security | **4/10** | SAAS-2 closed 2026-08-22. Still no edge, no TLS, no `dbfilter` |
| Tenant isolation | **2/10** | Substrate primitives are good; nothing above them exists |
| Data integrity | **5/10** | OPS-1 **fixed 2026-08-14** — no data was lost; reconciliation confirmed 0 business attachments missing. Remaining: no rehearsed backup (SUP-2, DAT-1) |
| Testing | 4/10 | Good volume, wrong layer |
| CI/CD | 0/10 | None |
| Documentation | 4/10 | Thorough but stale by 8× |

---

## 2. Top 10 risks

| # | Risk | ID |
|---|---|---|
| ~~1~~ | ~~**One unauthenticated POST claims the cluster master password**~~ — **FIXED 2026-08-22.** Rotated to a 32-character random value, stored hashed; `verify_admin_password('admin')` is now False | SAAS-2 |
| ~~2~~ | ~~**A filed VAT return reports nil while sales exist**~~ — **tags backfilled 2026-08-23** (0 to 16 links), so a tagged entry now reaches the return. It still cannot produce a *filing*: the IRD box layout is SME-gated and absent here, and no journal item carries a tax | FIN-1 |
| ~~3~~ | ~~**Balance Sheet, P&L and Cash Flow cannot render at all**~~ — **FIXED 2026-08-15.** All three render, print to PDF, and drill down to the entries behind each figure | FIN-2 |
| ~~4~~ | ~~Attachments written to an orphaned filestore~~ — **FIXED 2026-08-14.** Reconciliation proved no data loss; the orphan held only regenerable asset bundles | OPS-1 |
| 5 | **Total loss of the codebase** — **43** commits on one disk (28 at audit time), and the sync substituting for a backup is also the corruption risk. With risks 3 and 4 closed, this is now the most consequential item on this list | SUP-2, DAT-1 |
| 6 | **Client accounting data in corporate cloud sync** — two full database dumps, 572 attachments, 75 live sessions, plaintext credentials | DAT-1 |
| 7 | **Any client can select any tenant** once `dbfilter` is unset, and `X-Forwarded-Host` is unpinned | SAAS-1, SAAS-3 |
| 8 | **Odoo security patches cannot be applied**, and the only upgrade path silently destroys 87 translation files | SUP-1, SUP-3 |
| ~~9~~ | ~~**Cross-company data exposure** — no record rules on any of ten company-scoped models~~ **RESOLVED 2026-08-23** — ten global rules, proved by negative control | SEC-2 |
| 10 | **Every correctness defect is hidden behind a green test** — including one that skips under exactly the condition indicating the bug | TST-1, FIN-2, ACC-1 |

---

## 3. Top 10 next actions

| # | Action | Addresses | Effort |
|---|---|---|---|
| ~~1~~ | ~~Set a strong `admin_passwd`, `list_db = False`~~ — **DONE 2026-08-22**, and stored hashed. Blocking `/web/database/*` at the edge is a server-side step; `deploy/README.md` now carries the rule | SAAS-2, OPS-2 | done |
| 2 | ~~Correct `addons_path`/`data_dir`~~ — **DONE 2026-08-14**, with a fail-fast guard added to both launchers | OPS-1 | done |
| 3 | Create a remote and push | SUP-2 | XS |
| ~~4~~ | ~~Rotate both credentials~~ — **DONE 2026-08-22.** `RECONNAISSANCE.md` redacted; history left, the old values being defaults made worthless by rotation | SEC-1 | done |
| 5 | Move client data and credentials out of cloud sync | DAT-1 | S–M |
| 6 | Rename the three report models so the statements render | FIN-2 | S |
| ~~7~~ | ~~Fix the skipping VAT test, **then** backfill the tax tags by migration~~ — **DONE 2026-08-23**, in that order, with the guard watched failing first | TST-1, FIN-1 | done |
| 8 | Declare and pin `nepali-datetime` so the suite installs at all | DEP-1 | XS |
| 9 | One command that runs all eight suites and reports skips | CI-1 | M |
| 10 | Wire `selftest.py` into the suite | BS-1 | S |

Items 1–5 are this week. 6–7 are the correctness blockers. 8–10 make everything after them
verifiable.

---

## 4. SaaS readiness — **2 / 10, not ready**

**There is no tenant, provisioning or routing code in the repository.** Tenant identity would be a
regex over `pg_database` and nothing else — no tenant model, no routing map, no provisioning, no
offboarding, no per-tenant backup.

Odoo's boundary is *the database name resolved per request*. Everything **downstream** of that
resolution is correctly per-tenant. Everything **upstream** — `dbfilter`, the `X-Odoo-Database`
header, `?db=`, the master password, the session store, cron, the connection pool — is
process-global. All seven tenant-isolation P0s live there, and **four of them are configuration**,
fixable in under a day.

Scale, with the arithmetic in [`SAAS_MULTI_TENANCY.md`](SAAS_MULTI_TENANCY.md): comfortable to
~50 tenants; the **connection pool** thrashes around 100 (it is global per process, not per
database); **cron** does not scale past low hundreds, because every sweep touches every database;
and the registry LRU plus memory breaks near 1000. Sharding is not an optimisation, it is the
mechanism.

The riskiest single edit in the pivot: `db_name = odoo19` currently constrains routing, `list_dbs`
**and** cron simultaneously. Removing it opens all three at once.

---

## 5. Tenant isolation — **2 / 10 as configured; the primitives are sound**

**What the substrate gets right, and must not be broken:**

- Per-database filestore, with traversal stripped in `_full_path`
- Per-database `res.users`; no global identity table
- **Session tokens HMAC'd with a per-database `database.secret`** — the strongest primitive in the
  stack, and the reason SAAS-1 is a *reachability* finding rather than a data-read one
- `list_dbs` scoped to role ownership, so a second cluster on a different role is invisible
- `odoo` is correctly **not** a superuser

**What does not hold:** the session store is one global directory, and `res.device.log._revoke`
can delete another tenant's session files — upstream's own comment names the attack and the guard
checks format and path but never ownership (SAAS-5).

**PostgreSQL:** a connection to database A genuinely cannot read database B. But the Odoo account
**can connect** to an unrelated 12 GB corporate database on the same cluster and enumerate its 52
table names — it cannot read a single row (I probed precisely). That is metadata exposure, P2, and
worth fixing with one `REVOKE`. New databases also default to `PUBLIC CONNECT`, and Odoo
deliberately re-grants `CREATE ON SCHEMA public` on every database it creates — both latent with
one role, both real the moment a reporting or metrics role is added.

**Nine executable isolation tests are specified in [`TESTING.md`](TESTING.md).** None exists.
Write them before the pivot, not after.

---

## 6. Accounting Nepal readiness — **not ready; four correctness blockers**

Well-engineered and, at audit time, unable to produce a correct statutory output. One of the three
defects below is now fixed; the statements work, the VAT return still does not.

- ~~**FIN-2** — the three financial statements cannot render.~~ **RESOLVED 2026-08-15**, and they are
  now interactive and printable.
- **FIN-1** — the VAT return computes every box as zero.
- ~~**ACC-3** — the Export fiscal position substitutes no tax, so exports are invoiced at 13%.~~
  **RESOLVED 2026-08-23** — exports now carry VAT 0%; domestic sales still carry 13%.
- ~~**ACC-2** — the Balance Sheet omits prior-year unallocated earnings, so it stops balancing after
  year one.~~ **RESOLVED 2026-08-23** — an *Unallocated Earnings (prior years)* line carries them.
- **ACC-1** — a foreign-currency loan posts its amounts as company currency. It balances, which is
  why the test passes.

**What is genuinely good:** the "all jurisdiction values are editable records" claim is real — I
verified it, and there are **zero percentages in the TDS source**. Both TDS and VAT ship with
empty tables by design. The chart is structurally valid Odoo. The one exception is the Nepali
fiscal-year boundary itself, hard-coded as `SHRAWAN`/`ASHAR` (ACC-7).

The SME sign-off register — chart per NFRS/NPSAS, TDS rates, IRD form layout, depreciation classes
— remains open, and the modules' own READMEs say so correctly: *post test transactions freely,
file nothing.*

---

## 7. Bikram Sambat — **8 / 10; the mathematics is flawless**

I verified all **46,022** supported days in both directions against the reference library: **zero
divergence**. The generated JavaScript table matches Python for all 1,512 year-month pairs. Fiscal
year ranges are exact and contiguous across 125 BS years — zero gaps, zero overlaps, correct leap
behaviour. Storage stays Gregorian and BS is presentation-only, which is the right design and is
implemented cleanly.

The risk is entirely peripheral:

- **BS-1** — the exhaustive cross-check exists, works, and **nothing runs it**. The manifest's
  central safety claim is enforced by a script nobody invokes.
- **BS-2** — `datetime` is declared supported with **zero** timezone normalisation; latent only
  because every current field is a `Date`.
- **BS-3** — search and group-by buckets stay Gregorian, so **every BS month is split**. This is
  where the localisation currently stops: dates display in BS right up until you report by period,
  which is most of what an accountant does.
- **BS-4** — a raw `KeyError` at the top of the range, reachable by default from BS 2097.

---

## 8. Odoo upgrade risk — **Medium; better than most**

No core Python or XML modified, no monkeypatching, no deprecated API, `models.Constraint` and
`@api.model_create_multi` used correctly, all `_inherit` usage correct, and only two xpaths in the
whole codebase — one of them exemplary.

Three real risks:

- **UPG-1 (P1)** — a data file rewrites three `res.groups` records owned by `account`, not
  `noupdate`. Any `-u account` silently reverts them and the Accounting/Review/Reporting menus
  vanish. Core modification wearing a data costume.
- **UPG-2 (P2)** — zero migration scripts and every module frozen at `19.0.1.0.0`, so Odoo never
  fires "outdated" and a version-comparison deploy skips them entirely, leaving stale views and
  **ACLs**.
- **`_read_group`** is the highest-probability API break at Odoo 20; it has changed shape in every
  recent major, and there is no public alternative since `read_group` is itself deprecated.

Highest blast radius: the `_get_view` override. If its contract changes in 20, every form and list
load for `account.move`, `account.move.line` and `account.payment` raises. It is, however, a
faithful copy of core's own pattern and I would not change the approach.

---

## 9. Recommended target architecture

Full diagram in [`ARCHITECTURE.md`](ARCHITECTURE.md). In short: an nginx edge that **pins
`X-Forwarded-Host`** and **blocks `/web/database/*`**; Odoo instances with an **anchored
`dbfilter`**, `list_db = False`, a strong master password, no `smtp_*`, the watchdog restored, and
a **cron allowlist**; PgBouncer in session mode beyond ~50 tenants; and PostgreSQL with one
database per tenant, `CONNECT` and `CREATE` revoked from `PUBLIC`, never superuser, and never
`dblink` in a template.

Provisioning must create databases through Odoo's own path so `database.secret` is fresh — that is
what makes cross-tenant sessions impossible. Offboarding must purge the shared session store,
which is the step most likely to be forgotten.

Since tenant scale and instance model are undecided, the thresholds where each mechanism breaks
are documented with the arithmetic rather than a target assumed.

---

## 10. Prioritised roadmap

Five phases with exit criteria in [`ROADMAP.md`](ROADMAP.md); **46 tickets across 9 epics** in
[`JIRA_BACKLOG.md`](JIRA_BACKLOG.md), **9 of them open Blockers** (11 marked Blocker; BUG-16 and
BUG-6 are done). The
ticket count read 44 and had already drifted before BUG-22 was added for TST-8; it is now counted
from the file.

1. **P0/P1 Safety** — takeover, filestore split, remote, rotation, cloud sync, the four accounting fixes
2. **Stabilization** — installability, one test command, fixtures, the BS cross-check
3. **SaaS Foundation** — isolation tests **first**, then routing, record rules, cron scoping, provisioning
4. **Hardening** — CI, upgrade safety, observability for the five silent failure modes
5. **Scale & Upgradeability** — PgBouncer, cron sharding, BS period reporting, the core-vendoring spike

One ordering deserves emphasis, and it recurs: **fix the test before the defect.** BUG-8 before
BUG-7; the render assertion in the same change as BUG-6.

---

## Corrections to the previous audit

Stated plainly rather than quietly amended:

1. **"The financial statements are locally built and work."** Wrong. They have never rendered
   (FIN-2). The previous audit cited them as evidence the suite was well built.
2. **"Tax tags exist but the template wires them to nothing."** Wrong diagnosis. The template *is*
   correct — the tag column is populated and matches upstream `l10n_uk` syntax. The live database
   is stale because Odoo applies chart templates at adoption, not on `-u`. The fix is a data
   migration, not a template edit (FIN-1).

---

## What is working well

- **Bikram Sambat mathematics** — verified exhaustively, not sampled.
- **Upgrade discipline** — one of the cleaner Odoo customisation codebases I have audited.
- **Jurisdiction values as data** — the claim is real and unusually well honoured.
- **Security fundamentals** — no injection anywhere, no dangerous primitives, ACLs complete, and
  the VAT evaluator genuinely blocks RCE with a test proving it.
- **Concurrency** — safe, and verified rather than assumed.
- **Vendored OCA has zero drift** — which is exactly what keeps the AGPL modification trigger
  unpulled.
- **The Linux deployment templates** are materially safer than the dev ones, with every delta
  tabulated and explained.
- **Commit messages** are genuinely good; several explain *why*.

## What should NOT be changed yet

- **Do not rewrite git history** before the remote question is settled — cheapest now, worse after
  a first push. Rotate the credentials regardless; that is what reduces risk.
- **Do not edit vendored OCA in place** (SEC-4/5/8/9, API-1) — it destroys the zero-drift property
  protecting the licence position.
- **Do not restructure the repository** (SUP-1/SUP-4) before the spike.
- **Do not delete the orphaned filestore** before reconciling it against `ir_attachment.store_fname`.
- **Do not remove `db_name`** until `dbfilter` is anchored *and* the cron list is scoped — it is
  currently holding three doors shut at once.
- **Do not tighten `ProtectSystem` to `strict`** before deciding the writable-`/opt/odoo` question.
- **Do not act on `NEPAL-ACCOUNTING-BUILD-PLAN.md` as written** — three of its phases are already built.

## Still needing human verification

- **TST-7** — whether `res.company` test writes accrete orphan companies across runs
- **DEP-2 / DEP-4** — current advisories for `PyPDF2 2.12.1` and the ~2-year-old Python 3.12 pins
  (no network access to a feed from this environment)
- **DAT-1** — whether the OneDrive tenant has Files On-Demand enabled
- **SAAS-13** — whether a shared CDN would key `/web/assets/any/…` across tenants
- **LIC-1** — the legal reading; facts established, interpretation belongs to counsel
- **What wrote to the orphaned filestore on 2026-08-14** — establish before reconciling
- **FIN-1** — whether the tag backfill is the *only* gap to a correct IRD return; that needs the
  SME sign-off already on the register
