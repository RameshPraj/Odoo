# Production Readiness

Findings by ID in [`BACKLOG.md`](BACKLOG.md).

## Verdict: **No-go**, single-tenant or multi-tenant

**Five** open blockers — one of the original six (OPS-1) was fixed on 2026-08-14. None requires a
redesign; four are configuration.

| # | Blocker | ID | Why |
|---|---|---|---|
| 1 | Live one-request cluster takeover | SAAS-2 | `verify_admin_password('admin')` is `True`; one unauthenticated POST claims the master password, which then authorises backup of every database |
| 2 | Statutory reports cannot render | FIN-2 | Balance Sheet, P&L and Cash Flow all raise `QWebError` — verified |
| 3 | VAT return computes nil | FIN-1 | Zero tag→repartition links in the live database |
| ~~4~~ | ~~Attachment storage is splitting~~ **RESOLVED 2026-08-14** | OPS-1 | Paths corrected; reconciliation proved no data loss; launchers now fail fast |
| 5 | No recoverable backup of code or data | SUP-2, DAT-1 | 28 commits on one disk; the sync substituting for a backup is also the corruption risk |
| 6 | Known credentials, database manager exposed | SEC-1, OPS-2 | Values in immutable git history |

**Additionally, for multi-tenant only:** SAAS-1, SAAS-3, SAAS-4, SAAS-5 and SAAS-6 must close
before a second tenant exists. They are not go-live blockers for a single-tenant install.

## Go-live gates

### Correctness
- [ ] **FIN-2** — reports render; a test asserts the HTML contains "TOTAL ASSETS"
- [ ] **FIN-1 + TST-1** — tags backfilled by migration; the guarding test cannot skip
- [ ] **ACC-3** — Export fiscal position actually substitutes tax
- [ ] **ACC-2** — Balance Sheet balances after year one
- [ ] **ACC-1** — loan currency closed, or the field removed
- [ ] **TST-5** — TDS certificate path tested; silent `getattr` defaults removed
- [ ] **SCH-2** — a representative dataset loaded and statements verified against hand-computed figures
- [ ] SME sign-off: chart per NFRS/NPSAS, TDS rates and thresholds, IRD form layout box by box, TDS certificate layout, depreciation classes

### Security
- [ ] **SAAS-2** — strong master password; `verify_admin_password('admin')` is False
- [ ] **OPS-2 / SAAS-6** — `list_db = False`; `/web/database/*` blocked at the edge
- [ ] **SEC-1** — both credentials rotated
- [ ] **DAT-1** — client data and credentials out of cloud sync; dumps relocated
- [ ] **SEC-2** — record rules on all ten company-scoped models, **before** a second company
- [ ] **SEC-6** — read-only role cannot rewrite a filed return
- [ ] **SEC-3** — `**` banned in the formula whitelist
- [ ] **PG-1 / PG-2 / PG-4** — revokes applied and baked into provisioning

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
- [ ] **DEP-1** — `nepali-datetime` declared and pinned so a rebuild is possible at all
- [ ] Backup **and restore** rehearsed, per tenant
- [ ] `wkhtmltopdf` installed — without the patched 0.12.6 build every PDF fails
- [ ] **OPS-4** — watchdog restored (already correct in the Linux template)
- [ ] **OPS-3** — systemd hardening, once the writable-`/opt/odoo` question is settled

### Verification
- [ ] **CI-1** — one command runs all eight suites and reports skip counts
- [ ] **QA-1** — ruff and `pylint-odoo` configured and running
- [ ] **UPG-1** — group changes survive `-u account`, asserted by a test
- [ ] **UPG-2** — module versions bump on change

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
| Logs | stdout → journald. No aggregation, retention or rotation |
| Metrics | None |
| Tracing | None |
| Health check | None — no endpoint, no probe |
| Alerting | None |
| Per-tenant attribution | **Partial** — SAAS-15: the log carries `dbname`, but it is `?` on the nodb path, i.e. exactly for failed logins, database-manager access and `X-Odoo-Database` probing |

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
