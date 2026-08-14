# Jira Backlog

Ready-to-create tickets for every **P0 and P1**, plus the P2s that share an epic. Findings
themselves live in [`BACKLOG.md`](BACKLOG.md).

**Effort** XS <½d · S ½–1d · M 2–3d · L 1–2w · XL >2w · **Priority** Blocker / Critical / Major / Minor

---

## EPIC-1 · Tenant isolation and the perimeter
*Odoo's boundary is the database resolved per request. Everything upstream of that resolution is
process-global.* **Findings** SAAS-1..6, SAAS-10..14

### BUG-1 — Unauthenticated cluster takeover via the database manager
**Bug · Blocker · XS · SAAS-2**

**Problem** `/web/database/create` (and duplicate/drop/backup/restore) is `auth="none"`,
`csrf=False`, and runs `if verify_admin_password('admin') and master_pwd: change_admin_password(...)`.
Verified: `verify_admin_password('admin')` returns **True** on this instance.

**Impact** One unauthenticated POST claims the cluster master password, which then authorises
`/web/database/backup` — a full `pg_dump` plus filestore zip — of every database. No rate limit,
no CSRF, no audit trail. Mitigated today only by the localhost bind that SaaS removes.

**Solution** Set a strong `admin_passwd`; `list_db = False`; block `/web/database/*` at the edge.

**Acceptance** `verify_admin_password('admin')` is False · `/web/database/manager` unreachable
externally · POST to `create` with an arbitrary `master_pwd` does not change the stored password.
**Tests** Isolation test 4 in [`TESTING.md`](TESTING.md). **Risks** None — pure hardening.
**Do this first.**

### BUG-2 — `dbfilter` unset lets a client select any tenant
**Bug · Blocker (multi-tenant) · S · SAAS-1, SAAS-4, SAAS-11**

**Problem** With no `dbfilter`, `db_filter()` returns every database (`http.py:425`), and
`_get_session_and_dbname` honours an `X-Odoo-Database` header (`:1835-1838`).
`/web/session/authenticate(db=…)` and `?db=` are gated only by that same function.

**Impact** Any client reaches any tenant's login, signup, password-reset and public controllers
from any host with no cookie, defeating every Host-based edge policy. Not a direct data read —
auth still applies — but it hands over the full authenticated attack surface of every tenant.

**Solution** `dbfilter = ^%d$`, **anchored** (`.match()` is a prefix match — SAAS-11), plus a
tenant naming convention.

**Acceptance** `X-Odoo-Database`, `?db=` and `authenticate(db=…)` all refuse a non-matching
database · a database named `<tenant>_staging` is unreachable from `<tenant>`'s host.
**Tests** Isolation test 2. **Dependencies** Must land before `db_name` is removed (see BUG-4).

### BUG-3 — nginx does not pin `X-Forwarded-Host`
**Bug · Blocker (multi-tenant) · XS · SAAS-3**

**Problem** `proxy_mode = True` makes werkzeug's `ProxyFix(x_host=1)` overwrite `HTTP_HOST` from
the client-supplied `X-Forwarded-Host`, which `db_filter` then uses for `%h`/`%d`. The documented
nginx sets four proxy headers but not this one, and nginx passes unknown client headers through.

**Impact** `X-Forwarded-Host: victim.example.com` routes into the victim tenant, bypassing the
Host boundary, TLS SNI and every edge rule.

**Solution** `proxy_set_header X-Forwarded-Host $host;` (and `X-Forwarded-Port`) in every location.
**Acceptance** A request with a forged header is routed by the real Host. **Tests** Isolation test 2.

### BUG-4 — Cron runs against every database, ignoring `dbfilter`
**Bug · Critical · M · SAAS-7**

**Problem** `cron_database_list()` returns `config['db_name'] or list_dbs(True)`, and `db_filter`
is never applied (`server.py:99-100`, `db.py:449`).

**Impact** A tenant hidden from HTTP still runs crons, sends `mail.mail` and executes
tenant-authored `ir.cron` Python. A "suspended" tenant is not suspended. **`db_name = odoo19` is
currently the only thing containing this** — removing it for multi-tenancy opens routing and cron
simultaneously.

**Solution** An explicit cron allowlist, or filter the list through `db_filter`.
**Acceptance** A suspended tenant executes no jobs and queues no mail. **Tests** Isolation test 6.
**Dependencies** BUG-2 must land in the same change as any `db_name` removal. **Risks** This is
the single riskiest edit in the SaaS pivot.

### BUG-5 — Cross-tenant session destruction
**Bug · Critical · M · SAAS-5**

**Problem** The session store is one global directory (`config.py:1019-1029`), and
`res.device.log._revoke` passes identifiers straight to it. The guard validates format and path
prefix but **never ownership** — upstream's own comment names this attack.

**Impact** An authenticated user in tenant A can unlink tenant B's session files: forced logout
and session DoS across tenants.

**Solution** Per-tenant session directories, or separate instances per tenant. Upstream issue —
report it. **Acceptance** A `res.device.log` row in A cannot delete a session belonging to B.
**Tests** Isolation test 1.

### TASK-1 — Block and harden the database-manager surface
**Task · Major · XS · SAAS-10**
`/web/database/manager` renders publicly even with `list_db = False` (no route-level guard). Block
`/web/database/` at nginx. **Acceptance** All `/web/database/*` return 404 externally.

---

## EPIC-2 · Statutory correctness
**Findings** FIN-1, FIN-2, TST-1, TST-5, ACC-1..3, SCH-2

### BUG-6 — Balance Sheet, P&L and Cash Flow cannot render
**Bug · Blocker · S · FIN-2**

**Problem** Odoo resolves a report's model as `report.<report_name>`
(`ir_actions_report.py:1121-1123`). The three AbstractModels are named
`report.account_financial_statements.balance_sheet` etc. while the reports declare
`…report_balance_sheet_document`. **Verified by execution:** the model resolves to `None` and
rendering raises `QWebError` for all three.

**Impact** The module's entire purpose has never worked. Any user selecting Balance Sheet gets a
traceback.

**Solution** Rename the three `_name`s to match.
**Acceptance** All three render HTTP 200 and the Balance Sheet HTML contains "TOTAL ASSETS".
**Tests** `_render_qweb_html(...)` in the suite — **one assertion would have caught this**.

### BUG-7 — VAT return computes every box as zero
**Bug · Blocker · M · FIN-1**

**Problem** `account_account_tag_account_tax_repartition_line_rel` has **0 rows**; no journal item
carries a tax tag. **The template is correct** — `repartition_line_ids/tag_ids` is populated and
the tags match on name, applicability and country. The live database is stale because Odoo applies
chart templates at **adoption**, not on `-u`.

**Impact** A filed IRD VAT return reports nil while sales exist. Regulatory.

**Solution** A data migration that re-applies the tax model for companies already on the `np`
chart. Core's reload path preserves `tag_ids` deliberately (`chart_template.py:422-427`). **Not** a
template edit. **Dependencies** UPG-2 (a version bump is needed for a migration to run at all).
**Acceptance** After migration, a posted invoice yields non-zero boxes tying to the ledger.
**Tests** BUG-8 — do not close this without it.

### BUG-8 — The test guarding BUG-7 disables itself
**Bug · Blocker · S · TST-1**

**Problem** `test_vat_return.py:81-83` skips when the sale tax has no tags — the condition that
*is* the defect. Verified firing on the live database.

**Solution** Build tax, tags and invoice as fixtures; assert exact box values; the test must not
be able to skip. **Acceptance** Reverting BUG-7's fix makes this test fail.
**Sequence: land this before BUG-7**, so you can watch it fail and then pass.

### BUG-9 — Loans post foreign-currency amounts as company currency
**Bug · Critical · S–M · ACC-1**

**Problem** `currency_id` is user-settable and exposed on the form; the schedule computes in it;
both posting paths write only `debit`/`credit` — company-currency columns — with no
`amount_currency`.

**Impact** A USD 100,000 loan in an NPR company posts NPR 100,000. It balances, so the existing
test passes, and the ledger is silently wrong by the FX rate.

**Solution** Either full multi-currency (`amount_currency` + conversion), or make `currency_id`
`related='company_id.currency_id', readonly=True` and remove it from the form — safer given the
module's stated scope. **Acceptance** A foreign-currency loan either posts correct
`amount_currency` values or cannot be created. **Tests** A multi-currency posting test.

### BUG-10 — Export fiscal position substitutes no tax
**Bug · Critical · XS + migration · ACC-3**
`original_tax_ids` is empty on both zero-rated taxes, so applying the Export position leaves VAT
13% on the line — exports invoiced at 13%. **Solution** Populate the column; same migration caveat
as BUG-7. **Acceptance** An export customer's invoice line carries the 0% tax.

### BUG-11 — Balance Sheet omits prior-year unallocated earnings
**Bug · Critical · S · ACC-2**
Assets and liabilities are cumulative since inception; the result added back covers only the
current fiscal year. After year one the sheet does not balance.
**Solution** Add an Unallocated Earnings line = P&L since inception − current year.
**Acceptance** A company with a prior-FY entry produces a balancing sheet. **Tests** Post a
prior-FY entry.

### BUG-12 — TDS certificate can silently report zero withheld
**Bug · Critical · S · TST-5**
`action_collect_lines` is the only path putting real figures on a statutory certificate, is
untested, and uses `getattr(line, 'base_amount', 0.0)` — a renamed field yields zero with no error.
**Solution** Test it against a real withholding line; replace the defaults with explicit access.

---

## EPIC-3 · Data protection and secrets
**Findings** SEC-1, DAT-1, DAT-2, OPS-1, OPS-2, PG-1, PG-2, PG-4

### BUG-13 — Config points at deleted directories; attachments splitting
**Bug · Blocker · ~~S + M~~ · OPS-1 · ✅ DONE 2026-08-14**

`addons_path` and `data_dir` referenced a path that no longer existed, so all 15 custom modules were
skipped and attachment reads failed against a stale filestore.

**Resolved.** Both paths corrected in `odoo.conf` (gitignored). Reconciliation proved **no data
loss**: 0 referenced blobs missing from both trees, and **0 business attachments** absent from the
live filestore. The only `Downloads`-exclusive content was 5 rows of compiled asset bundles written
during the broken window.

**Verified** 134 modules load (was 125) · zero `no such directory` warnings · zero
`FileNotFoundError` · 986/991 blobs resolve · three real business attachments download over HTTP
with byte-exact sizes.

**Prevention shipped** `run-odoo.ps1` and `run-odoo.sh` now parse `addons_path` and `data_dir` and
exit non-zero if any entry is missing — tested at every failure position. Necessary because Odoo
treats both as non-fatal: `_file_read` catches `OSError`, logs at INFO and returns `b''`
(`ir_attachment.py:151-155`), so the server looked healthy throughout.

**Risk note now closed** The original warning — *"do not delete the orphan, it may hold the only
copy of recent attachments"* — was **disproven by measurement**. It holds nothing of value. See
TASK-4b.

### TASK-4b — Delete the orphaned `Downloads` tree
**Task · Minor · XS · DAT-2 · awaiting approval**
Reconciled: 11 files, all either regenerable asset bundles or referenced by no database row. **Zero
business attachments.** Deleting it leaves 5 dangling `ir_attachment` rows which return `b''`
harmlessly. Destructive, so not done without explicit approval.

### TASK-2 — Rotate credentials
**Task · Blocker · S · SEC-1**
The live master and database passwords are in immutable git history. Rotate both; redact the
document. **Risks** Removing the file does not undo history. Decide history rewriting separately —
cheapest **before** the first push (TASK-3).

### BUG-14 — Client data and credentials in corporate cloud sync
**Bug · Blocker · S–M · DAT-1**
Two full `pg_dump` images, the 113 MB filestore, 75 live session files, `odoo.conf` and a 337 MB
`.git` inside a syncing OneDrive folder. **Acceptance** Tree outside the sync root, or `.git`,
`.odoo_data` and `venv` excluded; dumps relocated. **Dependencies** After BUG-13 and TASK-3.

### TASK-3 — Create a remote and push
**Task · Blocker · XS · SUP-2**
28 commits on one disk, no remote, nothing ever reviewed. **Acceptance** History present on a
private remote; `git fsck` clean.

### TASK-4 — PostgreSQL revokes
**Task · Major · S · PG-1, PG-2, PG-4**
`REVOKE CONNECT ON DATABASE ist_datahub FROM PUBLIC` (the Odoo account can currently connect to an
unrelated 12 GB corporate database and enumerate 52 table names — it cannot read them). Bake
`REVOKE CONNECT` and `REVOKE CREATE ON SCHEMA public` into provisioning.
**Acceptance** A second login role cannot connect to any tenant database. **Tests** Isolation test 5.

---

## EPIC-4 · Multi-company and application security
**Findings** SEC-2, SEC-3, SEC-6, SEC-4, SEC-5, SEC-7, SEC-8

### BUG-15 — No record rules on any local model
**Bug · Critical · S · SEC-2**
Zero `ir.rule` across eight modules while ten models carry `company_id`. Every vendored OCA module
ships one. **Impact** Company A's accountant reads and edits company B's loans, TDS schedule and
filed VAT returns. **Acceptance** One rule per model; a non-skipping test proves A cannot read B.
**Dependencies** Must land before a second company or tenant exists.

### BUG-16 — Read-only role can rewrite a filed VAT return
**Bug · Major · XS · SEC-6** → `1,0,0,0` on `l10n_np.vat.return.line`.

### BUG-17 — VAT formula whitelist admits `**`
**Bug · Major · XS · SEC-3**
Verified: `9**9**9` passes `fullmatch` and hangs the worker; with `workers=0` and
`limit_time_real=0` it takes the server down. RCE **is** correctly blocked and tested.
**Acceptance** `9**9**9` raises `UserError`.

### TASK-5 — Local overrides for vendored OCA issues
**Task · Minor · S · SEC-4, SEC-5, SEC-8**
**Risks** Must be **local overrides**, not edits in place — editing vendored code destroys the
zero-drift property protecting LIC-1.

---

## EPIC-5 · Build reproducibility, CI and upgrade safety
**Findings** CI-1, CI-2, DEP-1, QA-1, UPG-1..4

### BUG-18 — Suite cannot be installed from a clean checkout
**Bug · Critical · XS · DEP-1**
`nepali_datetime` is declared in `external_dependencies` (which pip never reads) and absent from
`requirements.txt`, so the whole suite is uninstallable on a fresh machine.
**Acceptance** A fresh venv installs all 15 modules. **Blocks** every CI ticket and DR restore.

### STORY-1 — One command runs every suite
**Story · Critical · M · CI-1, TST-3**
**Acceptance** One documented command runs all eight suites on Windows and Linux · **reports skip
counts** · non-zero exit on failure. **Dependencies** BUG-18.

### STORY-2 — CI on push, with linting
**Story · Critical · M · CI-1, QA-1**
Ruff and `pylint-odoo` with a committed config matching the existing `# noqa` suppressions.
**Dependencies** STORY-1, TASK-3.

### BUG-19 — Local module overwrites core `account.*` groups
**Bug · Critical · S · UPG-1**
Three `res.groups` records owned by `account`, not `noupdate`, so any `-u account` silently
reverts them and the Accounting/Review/Reporting menus vanish.
**Solution** Idempotent `post_init_hook`. **Acceptance** After `-u account`, `group_account_manager`
still implies `group_account_user` — asserted by a test **run after `-u account`**.

### TASK-6 — Version bumps and migration scaffolding
**Task · Major · S · UPG-2**
All eight modules frozen at `19.0.1.0.0`; zero `migrations/`. **Blocks** BUG-7.
**Acceptance** Versions bump on change; a CI check flags a changed module with an unchanged version.

### TASK-7 — Re-anchor the settings xpath; rename `account.lock.dates`
**Task · Minor · S · UPG-3, UPG-4**
`//block[@id='analytic']` is sibling-relative into the most-churned arch in Odoo; a rename means
**the module fails to install**. And `account.lock.dates` sits in core's namespace.

---

## EPIC-6 · Bikram Sambat
**Findings** BS-1..8

### TASK-8 — Wire `selftest.py` into the test suite
**Task · Critical · S · BS-1**
The only exhaustive Python↔JS cross-check exists, works, and is invoked by nothing. The manifest's
central safety claim is enforced by a script nobody runs.
**Acceptance** The 46,022-day sweep runs in CI. **Highest value per unit effort in the audit.**

### BUG-20 — `datetime` declared supported with no timezone handling
**Bug · Critical · S · BS-2**
`supportedTypes` includes `"datetime"` but the widget reads browser-local components with zero
zone normalisation. Latent — every current field is a `Date` — but invited.
**Solution** Drop `"datetime"`, or anchor to `res.users.tz`. **Acceptance** A datetime at 23:30
Kathmandu renders the same BS day regardless of browser timezone.

### BUG-21 — Raw `KeyError` at the top of the supported range
**Bug · Major · XS · BS-4**
`month_length()` is the one entry point without error wrapping; `_fiscal_year_range(2100)` raises
`KeyError` past the wizard's `UserError`-only catch. Reachable **by default** from BS 2097.

### STORY-3 — BS-aware period filters and group-by
**Story · Major · L · BS-3**
Search and group-by buckets stay Gregorian, so every BS month is split. **This is the point where
the localisation currently stops** — BS displays until you report by period, which is most of what
an accountant does. **Acceptance** A "this BS month" filter and a BS month group-by exist and
match the fiscal calendar.

---

## EPIC-7 · Test integrity
**Findings** TST-2, TST-4, TST-6, TST-7, COD-1, COD-2

### STORY-4 — Fixtures instead of live database state
**Story · Critical · M · TST-2**
Five suites assert on ambient state; three assert the database is *empty* and fail permanently
once the modules are used as intended. The correct pattern exists in one module and was never
propagated. **Acceptance** Every suite passes on both an empty and a fully configured database.

### TASK-9 — JavaScript test suite
**Task · Major · M · TST-4** — 669 lines, zero tests; `static/tests/` is empty and untracked.

### TASK-10 — Shared XML well-formedness mixin
**Task · Major · S · COD-2** — copy-pasted 5×, missing from 3 of 8, and four copies use `minidom`,
which cannot catch the defect they exist for.

### TASK-11 — Precision-safe monetary assertions
**Task · Minor · S · COD-1, COD-7, TST-6**

### STORY-5 — Cross-tenant isolation suite
**Story · Blocker (multi-tenant) · L · all SAAS findings**
The nine tests specified in [`TESTING.md`](TESTING.md). **Write before the SaaS pivot, not after.**

---

## EPIC-8 · Licence and documentation
**Findings** LIC-1, DOC-1..4, N-1

### TASK-12 — Correct `VENDORED.md`
**Task · Major · S · DOC-3** — omits `date_range`; says "two of the three are AGPL-3" when it is
**four of seven**; lists 2 of 8 local modules; misstates the §13 trigger as modification.
**Do this before SPIKE-2** so the legal decision rests on correct facts.

### SPIKE-2 — Decide the AGPL position
**Spike · Critical · S once counsel responds · LIC-1**
Four vendored modules are AGPL-3; the app declares LGPL-3 and depends on three, and
`l10n_np_fiscal_year` *overrides* one. Lawful, but the combined work is effectively AGPL-3 and the
manifests misstate what a recipient receives. **SaaS is precisely the trigger** — §13 engages on
network provision to third parties. **Dependencies** TASK-12.

### TASK-13 — Project README and document dating
**Task · Critical · S · DOC-1, DOC-2, DOC-4**
`README.md` is upstream Odoo's; the build plan claims no code is written while three of its phases
are committed under its own names, with every test count wrong.

### TASK-14 — Rename `l10n_ne/`; remove empty directories
**Task · Minor · XS · N-1, COD-3, PKG-1**

---

## EPIC-9 · Supply chain
**Findings** SUP-1, SUP-3, SUP-4, DEP-5, API-1

### SPIKE-1 — Decide how Odoo core is obtained
**Spike · Critical · M spike → XL implementation · SUP-1, SUP-4**
51,775 files committed as an sdist with no remote; security patches cannot be merged.
**Acceptance** A written comparison of pinned-dependency vs submodule vs re-base vs status quo,
covering merge ability, clone size, review ergonomics, effect on SUP-3, migration cost and
rollback — plus a recommendation. **Dependencies** TASK-3. **Do last and deliberately.**

### TASK-15 — Upgrade runbook that regenerates translations
**Task · Critical · M · SUP-3**
The only upgrade path destroys 87 `i18n_extra` files, silently reverting code translations while
model translations survive. **Acceptance** A runbook with regeneration as a mandatory step, plus a
health check that fails below the expected file count. Declare `polib`.

### TASK-16 — Record vendored OCA provenance as SHAs
**Task · Major · S · DEP-5**

---

## Summary

| Epic | Tickets | Blockers | Critical |
|---|---:|---:|---:|
| 1 Tenant isolation | 6 | 3 | 2 |
| 2 Statutory correctness | 7 | 3 | 4 |
| 3 Data & secrets | 5 | 3 | 0 |
| 4 App security | 4 | 0 | 1 |
| 5 Build & upgrade | 6 | 0 | 4 |
| 6 Bikram Sambat | 4 | 0 | 2 |
| 7 Test integrity | 5 | 1 | 2 |
| 8 Licence & docs | 4 | 0 | 2 |
| 9 Supply chain | 3 | 0 | 2 |
| **Total** | **44** | **10** | **19** |

**The ten Blockers** — BUG-1 (cluster takeover), BUG-2 (`dbfilter`), BUG-3 (`X-Forwarded-Host`),
BUG-6 (reports), BUG-7 (VAT nil), BUG-8 (the test hiding it), BUG-13 (filestore split), BUG-14
(cloud sync), TASK-2 (rotate), TASK-3 (remote), plus STORY-5 for multi-tenant.
