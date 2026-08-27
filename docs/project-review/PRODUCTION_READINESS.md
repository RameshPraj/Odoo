# Production Readiness

Findings by ID in [`BACKLOG.md`](BACKLOG.md).

## Verdict: **No-go**, single-tenant or multi-tenant

**Two** open blockers of the original six. Resolved: OPS-1 (2026-08-14), FIN-2 (2026-08-15), and
SAAS-2 with SEC-1/OPS-2 (2026-08-22). All are struck through below rather than deleted, so the list
still reads as a history.

What remains is **FIN-1** (the VAT return computes nil) and **SUP-2/DAT-1** (no recoverable backup).
Neither needs a redesign: FIN-1 is a data migration, and SUP-2 is now purely a decision about where
the code should live.

| # | Blocker | ID | Why |
|---|---|---|---|
| ~~1~~ | ~~Live one-request cluster takeover~~ **RESOLVED 2026-08-22** | SAAS-2 | Master password rotated to a 32-character random value and stored hashed, so `verify_admin_password('admin')` is False and the takeover branch is unreachable |
| ~~2~~ | ~~Statutory reports cannot render~~ **RESOLVED 2026-08-15** | FIN-2 | All three now render, print to PDF, and drill down to the entries behind each figure. `TestReportsActuallyRender` renders them through the report engine, which is the check that was missing |
| ~~3~~ | ~~VAT return computes nil~~ **PARTIALLY RESOLVED 2026-08-23** | FIN-1 | Tags backfilled 0 to 16 by migration, so a tagged entry now reaches the return. Still **not a usable filing**: the IRD box layout is SME-gated and absent from this repo, and there are zero taxable journal items to report on |
| ~~4~~ | ~~Attachment storage is splitting~~ **RESOLVED 2026-08-14** | OPS-1 | Paths corrected; reconciliation proved no data loss; launchers now fail fast |
| 5 | No recoverable backup of code or data | SUP-2, DAT-1 | **43 commits** on one disk (28 at audit time); the sync substituting for a backup is also the corruption risk. Now the largest open risk on this list, since the two above it are closed. The SEC-1 objection is gone: those credentials were rotated 2026-08-22, so pushing publishes nothing usable. This is now purely a decision about where the code should live |
| ~~6~~ | ~~Known credentials, database manager exposed~~ **RESOLVED 2026-08-22** | SEC-1, OPS-2 | Both credentials rotated, master password now stored hashed, `RECONNAISSANCE.md` redacted, `list_db = False`. History deliberately not rewritten: the leaked values were the defaults `admin` and `odoo`, worthless once rotated |

**Additionally, for multi-tenant only:** SAAS-1, SAAS-3, SAAS-4, SAAS-5 and SAAS-6 must close
before a second tenant exists. They are not go-live blockers for a single-tenant install.

## Go-live gates

### Correctness
- [x] **FIN-2** — reports render; `TestReportsActuallyRender` drives them through the report engine (2026-08-15). This checkbox stayed unticked for eight days while the blocker table in this same file recorded it resolved — corrected 2026-08-23
- [x] **FIN-1 + TST-1** — tags backfilled by migration (0 to 16 links); the guarding test cannot skip and was watched failing first (2026-08-23)
- [x] **ACC-3** — Export fiscal position substitutes tax: export invoice `VAT 0% / tax=0.00`, domestic still `VAT 13% / tax=130.00`, both verified on the live database (2026-08-23)
- [x] **ACC-2** — Balance Sheet balances after year one: an *Unallocated Earnings (prior years)* line carries the P&L that Community never closes into equity (2026-08-23). Watched failing first — a prior-year entry produced "Balance sheet out by -50000.0"
- [ ] **ACC-1** — loan currency closed, or the field removed
- [x] **TST-5** — TDS certificate path tested through a real posted withholding line, and the `getattr` defaults removed (2026-08-23). The path did not merely risk reporting zero: it queried an AbstractModel with no table and could never run. Certificate **layout** still needs an SME
- [ ] **SCH-2** — a representative dataset loaded and statements verified against hand-computed figures
- [ ] SME sign-off: chart per NFRS/NPSAS, TDS rates and thresholds, IRD form layout box by box, TDS certificate layout, depreciation classes

### Security
- [x] **SAAS-2** — strong master password, stored hashed; `verify_admin_password('admin')` is False (2026-08-22)
- [x] **OPS-2** — `list_db = False` (2026-08-22)
- [ ] **SAAS-6** — `/web/database/*` blocked at the edge. Not applicable on this loopback-bound dev host; `deploy/README.md` now ships the nginx rule, so this is a server-side gate
- [x] **SEC-1** — both credentials rotated and the document redacted (2026-08-22)
- [ ] **DAT-1** — client data and credentials out of cloud sync; dumps relocated
- [x] **SEC-2** — ten global record rules across the three modules that own company-scoped models (2026-08-23). Negative control: with them disabled a company A manager reads company B's filed VAT return; with them active, refused
- [x] **SEC-6** — the read-only role is read-only on return lines (2026-08-23). Not the "one-character fix" the note claimed: that row was also what granted every higher group its access, so the billing role needed its own row or computing a return would have broken
- [x] **SEC-3** — the formula evaluator parses and walks an AST instead of calling `eval`, so `ast.Pow` is absent by construction rather than blacklisted (2026-08-23). A character class cannot express "one star but not two", which is why the regex admitted `**`
- [ ] **PG-2 / PG-4** — revokes baked into provisioning, before any second database role exists. **PG-1 is excluded**: its revoke alters `ist_datahub`, a third-party corporate database, so it is the owner's action or an accepted risk — not a change this project makes

### Multi-tenant (additional)
- [ ] **SAAS-1 / SAAS-11** — anchored `dbfilter`; `X-Odoo-Database` cannot select a tenant
- [ ] **SAAS-3** — nginx pins `X-Forwarded-Host`
- [ ] **SAAS-7** — cron scoped to an allowlist, verified after `db_name` is removed
- [ ] **SAAS-8** — PgBouncer, before ~50 tenants
- [ ] **SAAS-9** — per-tenant `ir.mail_server`; no `smtp_*` in `odoo.conf`
- [ ] The nine cross-tenant isolation tests in [`TESTING.md`](TESTING.md) exist and pass
- [ ] Provisioning and offboarding are scripted and tested, including session purge

### Operations
- [x] **OPS-1** — config paths corrected, filestores reconciled, launcher guard added (2026-08-14)
- [ ] **SUP-2** — remote created, history pushed
- [x] **DEP-1** — `nepali-datetime==1.0.8.5` pinned in `requirements.txt` and declared in `nepali_calendar_core`'s `external_dependencies`
- [ ] Backup **and restore** rehearsed, per tenant
- [ ] `wkhtmltopdf` installed **on the server** — without a patched-Qt build every PDF degrades to
      HTML, and an *unpatched* build passes silently while dropping headers and footers. Done on the
      dev host 2026-08-15 (`.runtime/bin/wkhtmltopdf/`, wired via `bin_path`); `doctor` now grades it.
      See `deploy/README.md` §1 and **DEP-6**
- [ ] **OPS-4** — watchdog restored (already correct in the Linux template)
- [ ] **OPS-3** — systemd hardening, once the writable-`/opt/odoo` question is settled

### Verification
- [x] **CI-1** — `run-odoo.ps1 test` / `run-odoo.sh test` run every suite and now report the skip count and each skipped test, with `-FailOnSkip` / `--fail-on-skip` for CI (2026-08-23). Verified against a deliberately skipped test: Odoo's own summary said "0 failed, 0 error(s) of 9 tests" while one test had skipped itself. **Automation itself still does not exist** — there is no runner invoking this on a push
- [x] **QA-1** — both installed, configured and clean (2026-08-23). ruff went 204 findings → 0, pylint-odoo → 0. It earned its place immediately: it caught an `F821 Undefined name` I introduced while renaming a lambda variable, which `py_compile` had passed
- [x] **UPG-1** — asserted by five tests, and **the premise was wrong** (2026-08-23). `-u` propagates to dependents, so `-u account` reloads `l10n_np_accounting` in the same transaction and it re-applies the wiring. Measured over three consecutive `-u account` runs: byte-identical. The prescribed `post_init_hook` would have been *worse* — it runs on install only
- [x] **UPG-2** — `tools/check_module_versions.py` compares each module's last code change against the last commit that moved its version line, and fails on drift; wired into `lint` (2026-08-23). It found six stale modules on first run, all now bumped. The check is the fix — bumping once would have been undone by the next change

### Legal
- [ ] **LIC-1** — AGPL position decided; manifests and `VENDORED.md` aligned. **SaaS is exactly
      the trigger**: §13 engages on network provision to third parties

## Backup and restore

**There is no backup.** Three things resemble one:

| Apparent backup | Why it is not |
|---|---|
| OneDrive sync | Not a git remote; also the leading corruption risk, and would replicate damage |
| Synced filestore | Only meaningful paired with a `pg_dump` from the same instant; a drifting copy matches no dump |
| The two `.dump` files | Development milestones, not a schedule |

A working arrangement needs three artefacts taken together and **rehearsed**: the database dump,
the filestore at the same instant, and the configuration. Restore currently also needs the manual
`nepali-datetime` install (DEP-1) and, after any Odoo upgrade, re-running `l10n_ne/apply.py`
(SUP-3). **An untested restore is a hypothesis.**

For multi-tenant, backup and restore must both be **per tenant**, and restore must produce a
**fresh `database.secret`** — otherwise a restored copy accepts the original's session tokens.

## Rollback

| Layer | Capability |
|---|---|
| Code | `git checkout` — but no remote, so only the local reflog protects you |
| Database schema | **None.** No migration scripts, and versions never change (UPG-2), so Odoo never runs one |
| Data | Restore from dump; loses everything since |
| Deployment | `systemctl restart`; no blue/green, no artefact to roll back to (CI-2) |

The UPG-2 consequence is worth stating plainly: because module versions never change, deploying
new code depends on someone remembering `-u`. Forget it and the database keeps old views, menus
and **access rights** while the source has moved on — a silent divergence that can leave stale
ACLs in place.

## Observability

Effectively none beyond Odoo's own log.

| Concern | State |
|---|---|
| Logs | stdout → journald; **`--logfile` when started through the launchers, with rotation** (OPS-6). Still no aggregation and no retention policy |
| Metrics | None |
| Tracing | None |
| Health check | **Endpoint exists and always did**; there is now a probe. See the correction below |
| Alerting | None |
| Per-tenant attribution | **Partial** — SAAS-15: the log carries `dbname`, but it is `?` on the nodb path, i.e. exactly for failed logins, database-manager access and `X-Odoo-Database` probing |

> **Correction to this section, recorded rather than silently amended.** The row above previously read
> "Health check | None — **no endpoint**, no probe". The endpoint half was wrong: Odoo 19 ships
> `/web/health` (`odoo/addons/web/controllers/home.py:172`), `auth='none'` and `save_session=False`, and
> `?db_server_status=1` additionally opens a `postgres` connection and returns HTTP 500 when PostgreSQL is
> unreachable. What was genuinely missing was a *probe*, which `run-odoo.ps1 health` /
> `./run-odoo.sh health` now provides, with exit codes 0/1/2 for automation. `save_session=False` matters:
> polling it does not litter `data_dir/sessions`, which a naive probe against `/web/login` would.

**Five failures would currently be silent**: SUP-3 (translations reverting after an upgrade),
FIN-1 (a return reporting nil), FIN-2 (reports raising for a user but not in tests), OPS-1
(attachments written to the wrong store — fixed, but the *class* of failure is unmonitored and
`_file_read` returns `b''` rather than raising), and any cross-tenant routing anomaly. None raises an
alert; all look like normal operation.

Monitoring should start with checks for exactly these, because they are the failures this system
actually has: an HTTP health check; an assertion that `data_dir` matches the expected path and is
writable; a count of `i18n_extra/ne.po` files; a computed VAT return being non-zero when tagged
move lines exist; a rendered statement returning HTTP 200; and a per-tenant request/error rate.

## Environment parity

Dev (Windows, `workers = 0`, watchdog off, `list_db = True`) and production (Linux, systemd,
multiprocessing, watchdog on, `list_db = False`) are structurally different and share **no build
artefact** (CI-2). They are related by a well-written prose table, not by anything executable.
`run-odoo.sh` and the systemd unit were added in the most recent commit and have never run.

## Operational risks not covered elsewhere

- **DAT-2** — an orphaned filestore in `Downloads`; no longer receiving writes since OPS-1 was fixed. Reconciled: nothing of value. Safe to delete, awaiting approval
- **N-1** — `l10n_ne/` shadows upstream Niger's localisation if the repo root ever joins `addons_path`
- **OPS-5** — `Restart=on-failure` with no `StartLimitBurst`: indefinite crash loop
- **SUP-3** — no upgrade procedure regenerates the translations it destroys
- The suite deliberately ships with **empty rate and form tables**. That is a correct and
  documented decision — but FIN-1 shows how easily "empty by design" and "silently zero" become
  indistinguishable to a user
