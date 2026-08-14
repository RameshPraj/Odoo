# BACKLOG — single source of truth

Every finding appears here exactly once. All other documents reference these IDs.

- **Audit date** 2026-08-14 · **Commit** `962b30b9` · working tree clean apart from `docs/`
- **Calibration** production with real client data · **multi-company** · **multi-tenant SaaS planned**
- **Confidence** `CONFIRMED` (read the source or ran it) · `LIKELY` · `POSSIBLE` · `NEEDS_VERIFICATION`
- **Effort** XS <½d · S ½–1d · M 2–3d · L 1–2w · XL >2w

**Totals: 9 × P0 · 24 × P1 · 31 × P2 · 18 × P3 · 6 × P4 = 88 findings**

> **This audit supersedes the first pass and corrects two of its conclusions.** Both corrections
> are stated explicitly at **FIN-1** and **FIN-2** rather than silently amended.

---

# P0 — Critical

## FIN-2 · Balance Sheet, P&L and Cash Flow cannot render
**CONFIRMED (by execution)** · Accounting · `account_financial_statements/`

Odoo resolves a report's data model as `report.<report_name>`
(`odoo/addons/base/models/ir_actions_report.py:1121-1123`). Declared vs actual:

| `report_name` (`report/financial_statements_templates.xml:199,207,292`) | AbstractModel `_name` |
|---|---|
| `account_financial_statements.report_balance_sheet_document` | `report.account_financial_statements.balance_sheet` (`financial_statements.py:131`) |
| `…report_profit_loss_document` | `report.account_financial_statements.profit_loss` (`:171`) |
| `…report_cash_flow_document` | `report.account_financial_statements.cash_flow` (`cash_flow.py:42`) |

**Evidence** — I rendered all three via `_render_qweb_html`. `_get_rendering_context_model`
returned **`None`** for every one and rendering raised **`QWebError`**. The templates then
dereference `wizard`, `assets`, `section` — variables the fallback context never sets.

**Impact** The module exists solely to supply these three statements. None has ever worked
end-to-end. Any user selecting Balance Sheet gets a traceback.

**Why nothing caught it** All 13 tests call `_get_report_values()` directly on the abstract
model, bypassing the report engine. `test_action_print_dispatches_on_report_type` asserts on the
`report_name` **string** and never renders.

> **Correction.** The previous audit rated these reports as working and cited them as evidence
> the suite was well built. That was wrong.

**Fix** Rename the three `_name`s to `report.<report_name>`; add a test asserting rendered HTML
contains "TOTAL ASSETS". **Effort S.**

## SAAS-2 · Live one-request cluster takeover via the database manager
**CONFIRMED (verified against the live config)** · SaaS · `odoo/addons/web/controllers/database.py:71-75`

```python
@http.route('/web/database/create', type='http', auth="none", methods=['POST'], csrf=False)
def create(self, master_pwd, name, lang, password, **post):
    insecure = odoo.tools.config.verify_admin_password('admin')
    if insecure and master_pwd:
        dispatch_rpc('db', 'change_admin_password', ["admin", master_pwd])
```

The same block appears on `duplicate` (`:96`), `drop` (`:113`), `backup` (`:129`) and
`restore` (`:152`) — all `auth="none"`, all `csrf=False`.

**Evidence** `config.verify_admin_password('admin')` returns **`True`** on this instance, so the
branch is live. `crypt_context` registers a `plaintext` scheme (`odoo/tools/config.py:21-23`),
and the shipped value is the product default.

**Impact** One unauthenticated POST sets the **cluster** master password to an attacker's value.
That password then authorises create / duplicate / drop / **backup** / restore of every database —
`/web/database/backup` streams a full `pg_dump` plus filestore zip. No rate limit, no lockout, no
CSRF, no audit trail. In DB-per-tenant this is every tenant's data.

**Mitigated today only by** `http_interface = 127.0.0.1`. SaaS removes that.

**Fix** Set a strong `admin_passwd` **now**; block `/web/database/` at the reverse proxy;
`list_db = False`. **Effort XS**, and it is the single highest-value action in this document.

## SAAS-1 · No `dbfilter` means the client chooses the tenant
**CONFIRMED** · SaaS · `odoo/http.py:402-425`, `:1835-1838`

With neither `dbfilter` nor `db_name` set, `db_filter()` falls through to `return list(dbs)`
(`:425`) — every database, unfiltered. `_get_session_and_dbname` then honours an
`X-Odoo-Database` request header (`:1835-1838`).

**Impact** Any client reaches any tenant's registry from any hostname with no cookie: login form,
`/web/session/authenticate`, password reset, signup, portal and every `auth='public'` controller.
It also defeats any per-tenant WAF, rate-limit or routing rule built on Host.

**Not a direct data read** — see SAAS-10 for what still holds. It hands an attacker the full
authenticated attack surface of every tenant.

**Fix** `dbfilter = ^%d$` (anchored) plus a tenant naming convention. **Effort S.**

## SAAS-3 · `proxy_mode` + unpinned `X-Forwarded-Host` = attacker-controlled tenant routing
**CONFIRMED (code) / LIKELY (this deployment)** · SaaS · `odoo/http.py:189-190, 2834-2841`

`ProxyFix(x_host=1)` **overwrites `HTTP_HOST` from the client-supplied `X-Forwarded-Host`**, and
`db_filter` then expands `%h`/`%d` from that rewritten value (`:409`).

**Evidence** `deploy/README.md:139-142` sets `Host`, `X-Real-IP`, `X-Forwarded-For`,
`X-Forwarded-Proto` — **not** `X-Forwarded-Host`. nginx forwards unrecognised client headers
verbatim. `deploy/odoo.conf.linux.example:37` sets `proxy_mode = True`.

**Impact** `Host: acme.example.com` + `X-Forwarded-Host: victim.example.com` routes into the
victim tenant, bypassing the Host-based boundary, TLS SNI and every edge policy.

**Fix** `proxy_set_header X-Forwarded-Host $host;` in every location block. **Effort XS.**

## SAAS-4 · `authenticate(db=…)` and `?db=` are gated only by `db_filter`
**CONFIRMED** · SaaS · `web/controllers/session.py:31-53`; `web/controllers/utils.py:59-78`

`/web/session/authenticate` takes an arbitrary `db` argument checked only by
`http.db_filter([db])` — called **without `host=`**, so it falls back to the request Host. Same
pattern for the `?db=` parameter in `ensure_db()`.

**Impact** One regex is the entire tenant boundary at the authentication endpoint. Compounds
SAAS-1. **Fix** as SAAS-1. **Effort** covered by SAAS-1.

## SAAS-5 · Cross-tenant session destruction
**CONFIRMED** · SaaS · `odoo/http.py:1121-1134`; `odoo/addons/base/models/res_device.py:187-188`

The session store is a **single global directory** with no database component
(`odoo/tools/config.py:1019-1029`) — contrast `config.filestore(dbname)` at `:1031`, which *is*
per-DB. `res.device.log._revoke` passes identifiers straight to it.

Upstream's own comment at `http.py:1125-1126` names this attack. The guard validates **format**
(42 base64 chars) and **path prefix** only — **never ownership**.

**Impact** An authenticated user in tenant A who can create a `res.device.log` row and call
`_revoke()` unlinks tenant B's session files: forced logout / session DoS across tenants.
Requires knowing the victim's identifier, so insider or chained — but there is no ownership check
at all. **Fix** Upstream issue; mitigate by per-tenant session directories or separate instances.
**Effort M.**

## SAAS-6 · `list_db = True` with `dbfilter` unset
**CONFIRMED** · SaaS · `odoo.conf:67`; `odoo.conf.example:76`

Combines SAAS-1 and SAAS-2 into a single exposed surface. `deploy/odoo.conf.linux.example:70-71`
gets both right — the dev configs are the documented starting point and do not. **Effort XS.**

## SUP-2 · No git remote — 28 commits on one disk, never reviewed
**CONFIRMED** · Repository

`git remote -v` empty; single ref `refs/heads/main`; no tags, no merges, no PRs.

**Impact** Total loss of all work if the disk or `.git` is damaged — and per DAT-1 the sync
product standing in for a backup is itself the leading corruption risk, so it would replicate
damage rather than protect against it. Combined with CI-1, **no change has ever been reviewed or
verified.** **Fix** Create a private remote and push. **Effort XS.**

## DAT-1 · Database dumps, filestore, live sessions and credentials in corporate cloud sync
**CONFIRMED** · Data protection

Inside `C:\Users\i81129\OneDrive - Verisk Analytics\Desktop\odoo-19.0`: two full `pg_dump` images
(9.3 + 9.5 MB), the 113 MB filestore (572 blobs), **75 live session files**, `odoo.conf` with the
master and database passwords, and a 337 MB `.git`. `.gitignore` has no bearing on file sync.

**Impact** *Confidentiality* — complete database images (user password hashes, partner PII, the
whole ledger) and session material replicated to a cloud tenant. *Integrity* — git assumes
exclusive local-filesystem semantics; a `gc`/`repack` racing the sync client is the classic
corruption case, and with no remote (SUP-2) the corrupted copy is the only copy.

**Refinement (2026-08-14, measured during the OPS-1 fix).** The **113 MB filestore is 98%
regenerable build artefacts** — 69 asset-bundle rows account for the 113 MB, while the actual
business content is **1.8 MB across 921 rows**. This lowers the *data-sensitivity* weight of the
filestore specifically. It changes **nothing else**: the two full `pg_dump` images, the 75 live
session files, `odoo.conf` with credentials, and the `.git` corruption risk are unaffected and
remain P0. Excluding `.odoo_data` from sync is now clearly the right call — it is mostly churn.

**Fix** Move the tree outside the sync root, or exclude `.git`, `.odoo_data`, `venv`; relocate the
dumps. **Effort S–M.**

## OPS-1 · Config points at deleted directories; attachments splitting across two filestores
**RESOLVED 2026-08-14** · Runtime configuration · `odoo.conf:24,27`

`addons_path` and `data_dir` referenced `C:\Users\i81129\Downloads\odoo-19.0\…`, which no longer
exists. Loading the registry emitted `Some modules are not loaded…` for all 15 custom modules, and
attachment reads raised `FileNotFoundError` against the stale filestore.

### Reconciliation result — no data was lost

Measured before any change, so it is not re-investigated:

| Measure | Value |
|---|---|
| `ir_attachment` rows | 1,276 (0 in `db_datas` — all filestore) |
| Rows with a blob | 991 → **574 unique** (Odoo dedupes by checksum) |
| Referenced blobs present **nowhere** | **0** |
| Referenced blobs only in `Downloads` | 2 unique / 5 rows |
| **Business attachments missing from OneDrive** | **0** (all 921 resolve) |

The 5 `Downloads`-only rows (ids 2108–2112, created 2026-08-14) are **compiled web asset bundles**
written during the broken window. Rows for the same bundle names from 2026-08-09/08-10 still exist
with present blobs.

### Fix applied
`addons_path` and `data_dir` corrected to the OneDrive paths. `odoo.conf` is gitignored, so this is
a local change. Both launchers now **refuse to start** if either path is missing — see the
prevention note below.

**Verified:** 134 modules load (was 125), zero `no such directory` warnings, zero
`FileNotFoundError`, 986/991 blobs resolve, and three real business attachments download over HTTP
with byte-exact sizes.

### Two corrections to this entry's original text
1. It said the orphan held business documents. It did not — only regenerable asset bundles.
2. An intermediate note claimed Odoo *regenerates* the missing bundles on demand. It did not:
   it served the **older, still-present** bundle versions. The 5 stale rows persist and now point
   at blobs that exist only in `Downloads`. They are harmless because `_file_read` catches
   `OSError`, logs at INFO and returns `b''` (`ir_attachment.py:151-155`) — which is precisely why
   this failure was silent rather than a 500.

### Prevention
Odoo treats both paths as non-fatal: a missing `addons_path` entry is logged and skipped, a stale
`data_dir` surfaces only as per-attachment INFO tracebacks. Both look like a healthy server.
`run-odoo.ps1` and `run-odoo.sh` now parse both settings and exit non-zero if any entry is absent,
tested at every failure position (first entry, last entry, `data_dir`, and both at once).

---

# P1 — High

## FIN-1 · VAT return computes every box as zero — *diagnosis corrected*
**CONFIRMED** · Accounting · live database state

The 8 Nepal tax tags exist with correct `name`, `applicability='taxes'`, `country_id=base.np`.
The relation table `account_account_tag_account_tax_repartition_line_rel` holds **0 rows**
cluster-wide; 0 journal items carry any tax tag. Every VAT box therefore evaluates to zero.

> **Correction.** The previous audit concluded "the template wires them to nothing." **That was
> wrong.** `account.tax-np.csv` column 12 `repartition_line_ids/tag_ids` **is** populated
> (`S_13 Base`, `S_13 Tax` on the VAT 13% rows), and the syntax matches upstream `l10n_uk`
> exactly. The live database is stale because Odoo applies chart templates at **adoption**, not
> on `-u`.

**Impact** A filed IRD VAT return reports nil while sales exist. Regulatory, not cosmetic.
**Fix** A data migration that re-applies the tax model to companies already on the `np` chart —
core's reload path preserves `tag_ids` deliberately (`chart_template.py:422-427`). **Not** a
template edit. **Effort M.**

## TST-1 · The test that would catch FIN-1 disables itself under exactly that condition
**CONFIRMED (skip fires today)** · Testing · `l10n_np_vat_return/tests/test_vat_return.py:81-83`

`if not tags: self.skipTest("sale tax has no tax tags configured in this chart")`. "No tags" is
not a precondition — it *is* the defect. Evaluated live: `VAT 13%`, `tags=0`, **skip fires**.

**Impact** The module reports green while never proving a box ties to the ledger. **Fix** Build
tax, tags and invoice as fixtures; assert exact box values; the test must not be able to skip.
**Effort S.**

## ACC-1 · Loans post foreign-currency amounts as company currency
**CONFIRMED** · Accounting · `l10n_np_loan/models/loan.py:286-297, 371-396`

`currency_id` is user-settable (`:39`) and exposed on the form under `base.group_multi_currency`
(`views/loan_views.xml:74`); the schedule computes and rounds in it (`:178`). Both posting paths
build move lines with **`debit`/`credit` only** — company-currency columns — and never set
`currency_id` or `amount_currency`.

**Impact** A USD 100,000 loan in an NPR company posts **NPR 100,000**. The entry balances, so
`test_drawdown_entry_is_balanced_and_hits_the_liability` passes, and the ledger is silently wrong
by the FX rate.

**Fix** Either add `currency_id` + `amount_currency` with conversion, or — safer given the
module's stated scope — make `currency_id` `related='company_id.currency_id', readonly=True` and
remove it from the form. **Effort S** (close the hole) / **M** (real multi-currency).

## ACC-2 · Balance Sheet omits prior-year unallocated earnings
**LIKELY** · Accounting · `account_financial_statements/models/financial_statements.py:146-149`

Assets and liabilities are cumulative since inception (`:139`, no lower bound), but the result
added back covers only the **current** fiscal year. Community posts no automatic year-end close,
so income and expense accumulate across years.

**Impact** `difference = Σ(prior years' P&L)`. After year one the sheet does not balance and a
"difference" line appears on a statutory statement. `test_balance_sheet_balances` posts only
current-FY entries, so it passes.

**Fix** Add an *Unallocated Earnings* line = P&L since inception − current year; test with a
prior-FY entry. **Effort S.**

## ACC-3 · Export fiscal position performs no tax substitution
**CONFIRMED** · Accounting · `l10n_np/data/template/account.tax-np.csv:10,14`

Odoo 19 expresses substitution through `account.tax.original_tax_ids`
(`odoo/addons/account/models/account_tax.py:102-114`). Both zero-rated NP taxes leave that column
**empty**. Upstream contrast: every non-domestic `l10n_uk` tax names the domestic taxes it
replaces.

**Impact** Applying the Export position leaves VAT 13% on the line — exports invoiced at 13%,
over-collection, wrong VAT return. **Fix** One cell each: `VAT_S_NP_13` / `VAT_P_NP_13`. Same
migration caveat as FIN-1. **Effort XS + migration.**

## UPG-1 · Local module overwrites core `account.*` group records
**CONFIRMED** · Upgrade safety · `l10n_np_accounting/security/account_groups.xml:32,39,49`

`<record id="account.group_account_readonly">` and two siblings rewrite records **owned by
`account`**, and they are not `noupdate`.

**Impact** Any `-u account` — including every 19.0.x point release — reloads them from upstream
XML, dropping `privilege_id`, `sequence`, the renames and the manager⇒user implication. The
Accounting / Review / Reporting menus silently vanish again. Uninstalling the module does **not**
revert them either. This is core modification wearing a data costume.

**Fix** Move to an idempotent `post_init_hook`; add a test asserting the implication holds, run
after `-u account`. **Effort S.**

## BS-1 · The exhaustive Python↔JS cross-check is dead code
**CONFIRMED** · Bikram Sambat · `l10n_np_bs/tools/selftest.py`

`selftest.py` performs exactly the 46,022-day sweep that proves the generated JS table matches
Python. It is not imported by `tests/__init__.py`, not called anywhere, and referenced only in
its own docstring and the manifest prose. `l10n_np_bs/__init__.py` is empty.

**Impact** The manifest's central safety claim — *"the Python and JS sides can never drift
apart"* — is enforced by a script nobody runs. Bumping `nepali_datetime` or hand-editing the
"DO NOT EDIT BY HAND" table would not be caught. **Fix** Wire it into the test suite. Highest
value per unit effort in the whole backlog. **Effort S.**

## BS-2 · `datetime` declared supported with zero timezone normalisation
**CONFIRMED** · Bikram Sambat · `l10n_np_bs/static/src/bs_date_field.js:44-55, 205`

`supportedTypes: ["date", "datetime"]`, but `get value()` returns the record value raw and
`adToBs(v.year, v.month, v.day)` reads **browser-local** components. There is no `setZone`,
`toUTC` or `toLocal` anywhere in the module. Odoo never assigns `luxon.Settings.defaultZone` in
production, so "default" is the browser OS zone, not `res.users.tz`.

**Impact** A datetime at `2026-09-08 19:00 UTC` renders BS 2083-05-24 in Kathmandu and
2083-05-23 in UTC — a day-boundary error for the 5h45m window each day. **Currently latent**:
every field in `_BS_DATE_FIELDS` is a `fields.Date` (verified at source), so no Datetime reaches
the widget today — but `supportedTypes` invites one.

**Fix** Either drop `"datetime"` from `supportedTypes`, or anchor to `res.users.tz` /
`Asia/Kathmandu`. **Effort S.**

## SAAS-7 · Cron enumerates all role-owned databases and ignores `dbfilter`
**CONFIRMED** · SaaS · `odoo/service/server.py:99-100`; `odoo/service/db.py:449`

`cron_database_list()` returns `config['db_name'] or list_dbs(True)`, and `list_dbs` selects
every database owned by the connecting role. **`db_filter` is never applied.**

**Impact** A tenant deliberately hidden from HTTP still runs its crons, sends `mail.mail` and
executes tenant-authored `ir.cron` Python. A "suspended" tenant is not suspended.
**`db_name = odoo19` is currently the only thing containing this** — removing it for
multi-tenancy opens routing *and* cron simultaneously. **Fix** Filter the cron list; keep an
explicit allowlist. **Effort M.**

## SAAS-8 · `db_maxconn` is a global per-process pool, not per-database
**CONFIRMED** · SaaS / PostgreSQL · `odoo/sql_db.py:816-832, 664-690`

`_Pool` is a module-level singleton sized `int(db_maxconn)`; connections are reusable only when
the DSN (including dbname) matches, and at cap the pool evicts an idle connection of any database
or raises `PoolError`.

**Impact** 64 connections shared across **all** tenants in a process. At ~100 tenants the pool
thrashes (evict-and-reconnect per request) before anything errors; bursts across >64 distinct
tenants surface as HTTP 500. In prefork with `workers = 5` the arithmetic reaches ~513 backends
against PostgreSQL's default `max_connections = 100` — PostgreSQL breaks first. Detailed
thresholds in `SAAS_MULTI_TENANCY.md`. **Fix** PgBouncer (session mode) + tenant sharding.
**Effort L.**

## SAAS-9 · Cluster-wide SMTP would share sender identity and reputation
**CONFIRMED (mechanism) / not currently triggered** · SaaS · `ir_mail_server.py:478-493, 646-663`

When a database has no `ir.mail_server`, `connect()` falls back to process-global `odoo.conf`
values, and `_get_default_bounce_address()` returns the single `config['email_from']` for every
tenant. Where the tenant address fails `from_filter`, the visible From is **rewritten** to the
shared identity.

**Impact if enabled** Every tenant's bounces to one mailbox; tenant mail visibly from your shared
identity; one tenant's spam poisons SPF/DKIM/IP reputation for all. **Correctly unset in all
three configs today — keep it that way.** **Fix** Provision a per-tenant `ir.mail_server` plus
per-tenant bounce/catchall at database creation. **Effort M.**

## SEC-1 · Live master and database passwords committed to a tracked document
**CONFIRMED** · Security · `RECONNAISSANCE.md:232,236,480`, commit `e4ff7dab`

The document reproduces the effective config verbatim, including the **current** values — and
flags them as critical while being the vehicle that publishes them. **Rotation is unavoidable**;
they are in immutable history. Compounds SAAS-2. **Effort S** (rotate) / **M** (history).

## SEC-2 · No record rules on any locally written model
**CONFIRMED** · Security · 10 models across 6 modules

Zero `ir.rule` records exist in any local module, while every new model carries `company_id`.
Every *vendored OCA* module ships one (e.g.
`account_fiscal_year/security/account_fiscal_year_rule.xml:13`).

**Impact** In a multi-company database, company A's accountant reads and edits company B's loans,
TDS schedule, VAT return forms and filed returns. Business logic filters by company, so computed
figures are right — the **records** are exposed. Rated P1 because multi-company is expected.
**Fix** One `ir.rule` per model, `['|',('company_id','=',False),('company_id','in',company_ids)]`;
test that A cannot read B. **Effort S.**

## SUP-1 · Odoo core is a source distribution committed to git with no upstream remote
**CONFIRMED** · Supply chain

51,775 of 52,523 tracked files (98.6%) are upstream Odoo. `PKG-INFO:3` reads
`19.0.post20260807`; `odoo.egg-info/` is present; no remote and no common ancestor with
`odoo/odoo`.

**Impact** Security releases cannot be merged — only bulk-overwritten, unreviewably. No
machine-checkable record of which build this is, so you cannot tell whether the core is patched.
**Fix** Spike: pinned dependency (conventional) vs submodule vs re-base. **Effort XL.**

## SUP-3 · 87 generated translation files inside the vendored core, destroyed by the only upgrade path
**CONFIRMED** · Supply chain · `l10n_ne/apply.py:176-182`, caveat at `:31-33`

Code translations resolve by module path, so `odoo/addons/<mod>/i18n_extra/ne.po` is genuinely the
only location — but nothing manages the consequence.

**Impact** Every upgrade silently reverts code strings to English while database-stored model
translations survive, leaving a **half-Nepali UI** — harder to spot than a clean revert. Recovery
is manual and needs `polib`, which is undeclared. **Fix** Scripted upgrade runbook + a health
check counting deployed files. **Effort M.**

## CI-1 · No CI of any kind — 121 tests, nothing runs them
**CONFIRMED** · Build

No `.github/`, `.gitlab-ci.yml`, `Jenkinsfile`, `tox.ini`, `pytest.ini`, pre-commit or Makefile.
Neither launcher passes `--test-enable`. There is no single command that runs all eight suites.

**Impact** Verification theatre. Four consecutive commits (`b2570489`, `d9b0bc4a`, `fcb814f3`,
`cb96ff96`) are same-day fixes for defects a test run would have caught. **Effort M.**

## DEP-1 · `nepali_datetime` undeclared — a clean build cannot install the suite
**RESOLVED** · Dependencies · was `l10n_np_bs/__manifest__.py:36`, now `nepali_calendar_core`

Declared in `external_dependencies`, which pip never reads; absent from `requirements.txt`;
present in the venv only because it was installed by hand; unpinned.

**Impact** `l10n_np_bs` refuses to install on a fresh machine, and the umbrella depends on it, so
**the entire suite is uninstallable**. Blocks CI, DR restore and any second developer.
**Effort XS.**

**Fixed.** `nepali-datetime==1.0.8.5` pinned in a marked project-additions block at the end of
`requirements.txt` — appended rather than merged alphabetically, so the stock-Odoo section stays
byte-identical and refreshing it from a newer Odoo release remains a readable diff.
`nepali_calendar_core/tests/test_requirements.py` fails if the pin is dropped by such a refresh,
drifts from the installed version, or is loosened to `>=`; the guard was verified by removing the line
and confirming the suite goes red. `deploy/README.md` no longer carries a separate unpinned
`pip install`. **COD-10 is narrowed but not closed:** the private `_days_in_month` is still private,
and there is now a test asserting it exists.

## TST-2 · Five suites assert on live database state; three break when the modules are used
**CONFIRMED** · Testing

`test_ships_with_no_form`, `test_ships_with_no_rates` and `test_is_configured_flag` assert
`search_count([]) == 0` — a property of the **database**, not the module. They fail permanently
once an accountant configures TDS rates or an IRD form.

The correct pattern exists at `test_np_fiscal_year.py:20-26` (creates its own company, after this
exact bug bit in `82f3ee43`) and was never propagated. **Effort M.**

## TST-5 · The only path producing real TDS figures is untested and fails silently
**CONFIRMED** · Testing · `l10n_np_tds/models/tds_certificate.py:58-96`

`action_collect_lines` duck-types with `getattr(line, 'base_amount', 0.0)`. No test calls it —
`test_tds.py` contains zero occurrences of `account.payment`, `withholding` or `action_post`.

**Impact** A wrong field name yields **zero withheld** on a statutory certificate, with no error.
**Effort S.**

## TST-4 · 669 lines of JavaScript with zero tests
**CONFIRMED** · Testing · `l10n_np_bs/static/src/`

`static/tests/` exists, is **empty**, and is untracked — so it vanishes on clone while the
manifest declares a bundle for it (`__manifest__.py:52`). No Hoot/QUnit file anywhere. The only
JS assertion checks a grid of >20 cells rendered and never validates a date. **Effort M.**

## LIC-1 · LGPL-3 manifests on what is legally an AGPL-3 combined work
**CONFIRMED (facts)** · Licence

Four of seven vendored OCA modules are AGPL-3. `l10n_np_accounting` declares LGPL-3 and depends
on three; `l10n_np_fiscal_year` declares LGPL-3 and **overrides** AGPL-3 `account_fiscal_year`.

The combination is lawful, but the combined work is effectively AGPL-3, so the manifests misstate
what a recipient receives. **AGPL §13 engages on network provision to third parties** — precisely
what SaaS is. **Fix** Business decision first, then align manifests and `VENDORED.md`.
**Effort S** once decided.

## OPS-2 · Database manager exposed with a default master password
**CONFIRMED** · Operations · `odoo.conf:8,67`

See SAAS-2 for the exploit path. **Effort XS.**

## SUP-4 · 98.6% vendored core makes review and provenance impractical
**CONFIRMED** · Supply chain · `.git` pack 327.82 MiB; tree 2.0 GB for ~17 MB of project work
(30:1). `git log --name-only` over any upstream-touching range is unusable. **Effort XL.**

## DOC-1 · Build plan says no code is written; three of its phases are built
**CONFIRMED** · Documentation · `NEPAL-ACCOUNTING-BUILD-PLAN.md:3,64,79-88`

Contradicts itself 54 lines later; all four per-module test counts are wrong (claims 7/13/8/9,
actual 5/7/7/13). Anyone planning from it would rebuild three completed modules. **Effort XS.**

## DOC-2 · README is upstream Odoo's, unmodified
**CONFIRMED** · Documentation · `README.md:1-38`

No mention of Nepal, `custom_addons/`, `deploy/`, the launchers, or how to run tests. The project
has no entry point. `RECONNAISSANCE.md` is stale throughout and two findings it raised itself
remain unfixed. **Effort S.**

## QA-1 · No linting configured, yet `# noqa` suppressions are scattered through the code
**CONFIRMED** · Quality · `vat_return.py:201` (`S307` on a live `eval()`), `bs.py:124`,
`test_menu_integrity.py:74,91`, 6 × `PLC0415`; `.gitignore:11` ignores `.ruff_cache/`

Ruff was run ad hoc and annotated; the config was never committed. The suppressions are
unenforceable folklore. **Effort S.**

---

# P2 — Medium

| ID | Conf. | Area | Location | Problem | Impact | Fix | Eff |
|---|---|---|---|---|---|---|---|
| **SAAS-10** | CONFIRMED | SaaS | `web/controllers/database.py:41-42,65` | `/web/database/manager` **renders publicly even with `list_db=False`** — no route-level guard; falls back to `[request.db]` | Leaks server version, language/country lists, `insecure` flag, current DB name; serves a public master-password form | Block `/web/database/` at nginx | XS |
| **SAAS-11** | CONFIRMED | SaaS | `odoo/http.py:418` | `dbfilter` uses `.match()`, not `.fullmatch()` | `^%d` matches `acme_staging`, `acme_backup` | Always anchor `^…$` | XS |
| **SAAS-12** | CONFIRMED | SaaS | `odoo/http.py:1099-1119` | Cross-tenant session-**existence** oracle via `get_missing_session_identifiers` | Confirmation channel for SAAS-5 | Per-tenant session dirs | M |
| **SAAS-13** | LIKELY | SaaS | `web/controllers/binary.py:99-102,142` | `/web/assets/**any**/…` bypasses the version check; no `Vary` on Host | Behind a shared CDN keyed on path, tenant A's bundle could be served to tenant B | Key cache on Host, or no shared CDN | S |
| **SAAS-14** | CONFIRMED | SaaS | `odoo/http.py:1069-1075` | Session vacuum is cluster-wide with one `SESSION_LIFETIME` | Per-tenant session policy impossible at the store | Accept, or separate instances | — |
| **PG-1** | CONFIRMED | PostgreSQL | live cluster | The `odoo` role **can connect** to an unrelated 12 GB corporate database (`ist_datahub`) and enumerate 52 table names — but **cannot read any** (0 selectable, no CREATE) | Metadata exposure; widens the blast radius of an Odoo compromise | `REVOKE CONNECT ON DATABASE ist_datahub FROM PUBLIC` | XS |
| **PG-2** | CONFIRMED | PostgreSQL | `datacl = NULL` on all DBs | New databases default to `PUBLIC CONNECT` | Harmless with one role; wrong the moment a reporting/metrics role exists | Revoke in provisioning | XS |
| **PG-3** | CONFIRMED | PostgreSQL | shared catalogs | From one tenant's connection, `pg_database`, `pg_roles`, `pg_stat_activity` enumerate all tenants | Tenant enumeration; other tenants' query strings visible in `pg_stat_activity` | `pg_stat_statements` restrictions; accept enumeration | S |
| **PG-4** | CONFIRMED | PostgreSQL | `odoo/service/db.py:168-174` | `GRANT CREATE ON SCHEMA PUBLIC TO PUBLIC` on every new database, undoing PG15 hardening | Latent with one role; any additional login role gains CREATE in every tenant DB | `REVOKE` in provisioning | S |
| **SEC-3** | CONFIRMED | Security | `vat_return.py:195,201` | Regex whitelist admits `**`; verified `9**9**9` passes `fullmatch` | Worker hang; with `workers=0` and `limit_time_real=0` the whole server. RCE **is** correctly blocked and tested | Ban `**`; add a test | XS |
| **SEC-6** | CONFIRMED | Security | `l10n_np_vat_return/security/ir.model.access.csv:8` | `group_account_readonly` given write/create/unlink on VAT return lines | A read-only accountant can rewrite a filed return | `1,0,0,0` | XS |
| **BS-3** | CONFIRMED | Bikram Sambat | `bs_accounting_dates.py:57-60`; `account_move_views.xml:365` | Search and group-by buckets stay Gregorian | A BS user filtering "August 2026" gets Bhadra 16 – Ashoj 15, straddling two BS months. **The most consequential functional gap** — BS presentation stops where periodic reporting begins | BS-aware period filter and group-by | L |
| **BS-4** | CONFIRMED | Bikram Sambat | `bs.py:121-124`; `generate_np_fiscal_year.py:53,69` | `month_length()` raises raw `KeyError` at BS 2101 — the one entry point with no error wrapping — escaping the wizard's `UserError`-only catch | Traceback instead of a message; reachable by default from BS 2097 | Wrap + bound-check | XS |
| **BS-5** | LIKELY | Bikram Sambat | `bs_date_field.xml:14-20` | Input is uncontrolled (`t-att-value` → `setAttribute`), so the DOM diverges from the record after typing | Rejected entries stay on screen; picker updates don't refresh the box | Use `useInputField` | S |
| **BS-6** | CONFIRMED | Bikram Sambat | `bs_date_field.js:127-130` | "Today" from the raw browser clock, not `res.users.tz` | Widget and server disagree on today for part of each day | Derive from user tz | S |
| **BS-7** | CONFIRMED | Bikram Sambat | `bs_accounting_dates.py:70-81` | Name-based patching walks nested subviews of **other** models | Latent today; a future non-date field named `date` in a subview gets `bs_date` | Check `_fields[name].type` | XS |
| **BS-8** | CONFIRMED | Bikram Sambat | `bs_accounting_dates.py:57-60` | Only `form` and `list` patched | Kanban, calendar, graph and **all PDF reports** stay Gregorian — internally inconsistent | Document; extend if wanted | S |
| **ACC-4** | CONFIRMED | Accounting | `account.fiscal.position-np.csv:3` | Export FP `auto_apply=1` with no country | Also zero-rates foreign **vendors** — wrong under reverse charge | SME decision | S |
| **ACC-5** | CONFIRMED | Accounting | `l10n_np/data/template/account.account-np.csv:24` | `Tax Receivable` typed `asset_current` but sits in the 2xxxxx liability block | Reads wrong on a code-ordered trial balance | Re-code or re-type | XS |
| **ACC-6** | CONFIRMED | Accounting | `l10n_np_tds/data/ir_sequence_data.xml:6,9` | TDS sequence uses the **Gregorian** year and is **company-global** (`company_id=False`) | All tenants share one certificate series; the year rolls mid-Nepali-FY | Per-company sequence, BS year | S |
| **UPG-2** | CONFIRMED | Upgrade | all 8 manifests | Zero migration scripts; every module frozen at `19.0.1.0.0` | Odoo never fires "outdated"; a deploy relying on version comparison skips them, leaving stale views and **ACLs** | Bump versions; add `migrations/` | S |
| **UPG-3** | CONFIRMED | Upgrade | `res_config_settings_views.xml:10` | xpath `//block[@id='analytic']` `position="before"` — sibling-relative into the most-churned arch in Odoo | A rename → `ParseError` → **the module fails to install** | Target the ancestor with `position="inside"` | S |
| **UPG-4** | POSSIBLE | Upgrade | `wizard/account_lock_dates.py:18` | New model named `account.lock.dates` — inside core's namespace | If Odoo 20 adds that name, this silently *extends* it and the fields collide | Rename `l10n_np.account.lock.dates` | XS |
| **DAT-2** | CONFIRMED | Data | `…\Downloads\odoo-19.0\.odoo_data` | Orphaned filestore, 11 files, no repo/config/owner. Caused by OPS-1, which is now fixed so it receives no further writes | **Reconciled 2026-08-14: contains nothing of value** — 5 regenerable asset bundles + 6 blobs referenced by no database row. **Zero business attachments.** Originally rated as holding business documents; that was wrong | Safe to delete. The 5 dangling rows then return `b''` per `ir_attachment.py:151-155` | XS |
| **SCH-1** | CONFIRMED | Schema | custom tables | Business FKs unindexed (`vat_return_line.return_id`, `.box_id`, `loan.partner_id`, `company_id`) | Low at present volume; `company_id` becomes hot once SEC-2 adds rules | `index=True` | XS |
| **SCH-2** | CONFIRMED | Schema | all custom tables | **0 rows**; 3 posted journal entries cluster-wide | Nothing exercised at volume; no performance claim is evidence-based | Load representative data | M |
| **COD-1** | CONFIRMED | Tests | `test_loan.py` (10 sites) | Money compared with `assertEqual`; the `currency.round()` mitigation appears in exactly one test | Brittle across rate/term combinations | Round consistently | S |
| **COD-2** | CONFIRMED | Tests | 5 modules | `test_xml_is_well_formed` copy-pasted 5×, **missing from 3 of 8**; four copies use `minidom`, which accepts `--` in comments where Odoo's `lxml` rejects it | Four copies cannot catch the defect they exist for | One shared `lxml` mixin | S |
| **COD-3** | CONFIRMED | Packaging | 3 dirs | Empty package directories on disk but untracked | `git clone` ≠ working copy; the declared JS test bundle location does not exist on a fresh clone | Delete or `.gitkeep` | XS |
| **SEC-4** | CONFIRMED | Security | `abstract_wizard.py:67-75` | `sudo()` writes a global `ir.default` on every Export click; wizards open to `base.group_user` | Any employee writes a company-wide default | Local override | S |
| **SEC-5** | CONFIRMED | Security | OCA ACL CSVs | `base.group_user` CRUD on budget lines and the persistent age-report configuration | Non-accounting staff alter aged-balance bucketing | Tighten locally | S |
| **SEC-7** | CONFIRMED | Security | `l10n_ne/apply.py:88,112,148,179-181` | `--modules` unvalidated into `os.path.join`; no containment check | Operator-run, so bounded — an unguarded footgun in a routine tool | `os.path.commonpath` | XS |
| **SEC-8** | CONFIRMED | Security | `report_xlsx/controllers/main.py:27,36-41,100-104` | Bare `@route()` inherits auth invisibly; client context merged into rendering; `_serialize_exception` returned | Auth tracks upstream silently; info disclosure (escaped, not XSS) | Restate `auth=`; allowlist context | S |
| **CI-2** | CONFIRMED | Environments | repo root | No Docker/compose; dev (Windows, `workers=0`) and prod (Linux, systemd) share no artefact; `run-odoo.sh` has never run | Nothing validates the Linux path | Containerise | M |
| **DEP-2** | CONFIRMED | Dependencies | `requirements.txt:66-67` | `PyPDF2==2.12.1` installed and active (retired upstream) | PDF parsing is an attack surface for uploaded invoices | Move to `pypdf` | S |
| **DOC-3** | CONFIRMED | Documentation | `custom_addons/VENDORED.md` | Omits `date_range`; "two of the three are AGPL-3" when it is **four of seven**; lists 2 of 8 local modules; misstates the §13 trigger as modification | Understates AGPL exposure by half; feeds LIC-1 | Rewrite against manifests | S |
| **DOC-4** | CONFIRMED | Documentation | 5 root docs | All describe a repo with one local module; `RUNTIME-ARCHITECTURE.md` never mentions `custom_addons` | Stale by 8×; omits the `_get_view` patcher | Date-stamp as snapshots | S |
| **OPS-3** | CONFIRMED | Operations | `deploy/odoo.service:18,51`; `README.md:45` | Service account owns `/opt/odoo` incl. its venv; `ProtectSystem=full` leaves `/opt` writable; missing `PrivateDevices`, `RestrictAddressFamilies`, `SystemCallFilter`, `MemoryMax`, `UMask`; `-s /bin/bash` | Code-execution bugs become persistent. Note the tension: `-u` and SUP-3 both want `/opt/odoo` writable | `ProtectSystem=strict` + `ReadWritePaths`; `nologin` | S |
| **OPS-4** | CONFIRMED | Operations | `odoo.conf:60`; `.example:68` | `limit_time_real = 0` disables the runaway-request watchdog | One tenant's infinite loop permanently consumes a thread — a cross-tenant availability path. The Windows rationale is sound for dev; it must not ship | Restore on Linux (already correct there) | XS |
| **TST-3** | CONFIRMED | Testing | `test_reconcile.py:48-50`; `test_bs_accounting_dates.py:42-46` | Whole suites gate on one skip; nothing reports skip counts | A green run is indistinguishable from a run of nothing | Fail CI on skips | S |
| **TST-6** | CONFIRMED | Testing | `test_loan.py:243-259` | Hardcoded 2026 backdates mixed with `context_today` | Holds only while the clock is past Feb 2026 | `freezegun` | XS |
| **TST-7** | NEEDS_VERIFICATION | Testing | `test_lock_dates.py:22,79`; `test_bs_accounting_dates.py:30` | ~7 throwaway `res.company` per run; `base.group_user.implied_ids` mutated globally | If `cr.precommit` writes survive rollback, runs accrete orphan companies, breaking TST-2's suites | Verify across two runs | S |
| **N-1** | CONFIRMED | Naming | repo root | `l10n_ne/` collides with upstream **Niger** (`ne` = Niger; Nepal is `np`); no manifest | Harmless until the repo root joins `addons_path` | Rename outside `l10n_*` | XS |

---

# P3 — Low

| ID | Conf. | Location | Problem |
|---|---|---|---|
| **BS-9** | CONFIRMED | `bs.py:107-109` vs `bs_convert.js:127-129` | Python/JS formatting and default digits diverge for the same option |
| **BS-10** | CONFIRMED | `bs.py:115` vs `bs_convert.js:135` | Parser divergence: JS accepts `.` and space separators, Python does not; JS returns null, Python raises |
| **BS-11** | CONFIRMED | `bs_convert.js:31-36` | `bsMonthLength` validates year but not month → `undefined` for month 13 |
| **BS-12** | CONFIRMED | `bs_convert.js:39-42` | `adToBs` does not validate Gregorian input; `Date.UTC` normalises `2026-09-31` silently |
| **BS-13** | CONFIRMED | `bs_date_field.xml:5-27` | For a datetime the time-of-day is invisible and uneditable; `clear()` wipes the whole value |
| **BS-14** | CONFIRMED | `generate_np_fiscal_year.py:108-113` | `fiscalyear_last_day` write-back contradicts the module's own premise; wrong by up to 2 days outside the generated span |
| **BS-15** | CONFIRMED | `generate_np_fiscal_year.py:88-97` | `overwrite` unlinks **any** overlapping fiscal year, no name filter, no confirmation |
| **BS-16** | CONFIRMED | `gen_js_data.py:45-49` | The generator's own guard probes only 5 dates; the strong check is the one not wired in (BS-1) |
| **BS-17** | CONFIRMED | `bs_calendar_action.js:91` vs `bs_date_field.js:159-183` | Saturday-as-weekend handled in the calendar, missing from the picker — two grids disagree |
| **BS-18** | CONFIRMED | module-wide | No Nepal timezone anchored anywhere (zero hits for `Kathmandu`/`Asia/`) — root cause of BS-2 and BS-6 |
| **COD-5** | CONFIRMED | `tds_certificate.py:80,92-94` | Defensive duck-typing against a pinned tree — unreachable one way, untested both |
| **COD-6** | CONFIRMED | 4 sites | Broad `except Exception` discarding tracebacks in production paths |
| **COD-7** | CONFIRMED | `test_loan.py:154`; `test_tds.py:95` | `assertRaises(Exception)` catches anything, including a typo in the test |
| **COD-8** | CONFIRMED | `test_menu_visibility.py` | Menu-tree walker written out three times in one file |
| **COD-9** | CONFIRMED | 4 modules | "date_from precedes date_to" reimplemented four times, four messages |
| **COD-10** | CONFIRMED | `bs.py:124`; `gen_js_data.py:17` | Private `nepali_datetime` API on an unpinned library |
| **UPG-5** | CONFIRMED | `financial_statements_templates.xml:42,132,221` | `wizard._fields[…].selection` — ORM internals inside QWeb |
| **UPG-6** | CONFIRMED | `l10n_np/data/res_country_state_data.xml:3` | Provinces `noupdate="1"` while self-flagged `NEEDS SME CONFIRMATION` — a later fix will not propagate |
| **ACC-7** | CONFIRMED | `generate_np_fiscal_year.py:12-13` | `SHRAWAN`/`ASHAR` hard-coded — the one genuine exception to "all jurisdiction values are records" |
| **SEC-9** | CONFIRMED | `report_xlsx_helper/report_xlsx_abstract.py:757,767` | `eval()` with **full builtins**; safe today (all call sites traced), invariant is a code comment |
| **SEC-10** | CONFIRMED | `general_ledger_wizard.py:94` | `literal_eval` on a user-editable domain `Char`; `safe_eval` is house style |
| **SEC-11** | CONFIRMED | `l10n_ne/apply.py:46-52` | `sys.path` prepended before importing `polib` |
| **API-1** | CONFIRMED | `account_financial_report/report/general_ledger.py:217` | Deprecated `read_group` (deprecated, **not** removed) — every sibling call in the same file was migrated; this one missed, on the least-tested branch |
| **DEP-3/4/5** | CONFIRMED / NEEDS_VERIFICATION | `requirements.txt`; `VENDORED.md:9-14` | Stock upstream with no project additions; Python-3.12 pins ~2 years stale; vendored provenance is branch URLs not SHAs, update procedure uses `--depth 1` |
| **DOC-5** | CONFIRMED | code-wide | **Zero** TODO/FIXME/HACK in local code — genuinely good, but deferred work lives in prose, so grepping returns a false all-clear |
| **QA-2** | CONFIRMED | 6 files | UTF-8 BOM as first byte |
| **SAAS-15** | CONFIRMED | `odoo/netsvc.py:172-177`; `odoo/http.py:446,2280` | Log lines carry `dbname`, but it is `?` for the nodb path — i.e. exactly the security-relevant events (failed logins, database-manager access, `X-Odoo-Database` probing) |
| **SAAS-16** | CONFIRMED | `odoo/netsvc.py:47-101` | `--log-db` writes every tenant's logs into one `ir_logging` table readable by that DB's users. Off by default; never point it at a tenant DB |

---

# P4 — Cleanup

| ID | Location | Problem |
|---|---|---|
| **PKG-1** | `l10n_np_bs/__manifest__.py:52` | Asset glob matches nothing (see COD-3, TST-4) |
| **PKG-2** | 5 manifests | `installable` / `application` keys inconsistently present |
| **QA-3** | `.gitignore:47` | Ignores `.claude/` wholesale, swallowing a future *shared* settings file |
| **OPS-5** | `deploy/odoo.service:37-38` | `Restart=on-failure`, `RestartSec=5s`, no `StartLimitBurst` — indefinite crash loop |
| **BS-19** | `bs.py:54` | `to_np_digits` raises on exotic digit characters (`'²'.isdigit()` is True) |
| **UPG-7** | `bs_accounting_dates.py` | `_BS_DATE_FIELDS` is a plain class attribute, not `_inherit`-merged — a second module adding the mixin would silently lose one set |

---

# Verified NOT problems

Recorded so they are not re-investigated.

**Bikram Sambat mathematics is exact.** All 46,022 supported days replayed in both directions
against `nepali_datetime`: **zero divergence**. The generated JS table matches the library for all
1,512 (year, month) pairs. Fiscal-year ranges are exact and contiguous across 125 BS years — zero
gaps, zero overlaps, no off-by-one at boundaries. Epoch consistent. All four month lengths
(29/30/31/32) present and handled. Boundary errors are symmetric between Python and JS.

**Upgrade discipline is genuinely good.** No core Python or XML modified (`git log` over `odoo/`
returns nothing but `i18n_extra`). No monkeypatching. No `_sql_constraints`, `@api.one/multi`,
`attrs=`, `states=`, `<tree>`, `name_get`, or legacy `Many2many` signatures. `models.Constraint`
and `@api.model_create_multi` used correctly. All `_inherit` usage correct; `_inherits` never
misused. `bs_accounting_dates.py` is a faithful copy of core's `res_currency` `_get_view` pattern,
including appending to the cache key rather than rebuilding it — the best-engineered part of the
codebase.

**Security fundamentals.** No SQL injection — every `cr.execute` parameterised, each read
individually. No `exec`, `os.system`, `subprocess`, `pickle`, `yaml.load`. Every concrete model
has an ACL. The VAT formula evaluator genuinely blocks RCE, with a test proving it. No XSS vector.

**Concurrency is safe.** REPEATABLE READ (`odoo/sql_db.py:373`) plus 5-try serialization retry
(`odoo/service/model.py:29-30`) makes the in-memory `state == 'posted'` checks sound. No row
locking needed.

**What the SaaS substrate gets right — do not break these.** Per-database filestore
(`config.py:1031`, with `..` stripped in `_full_path`). Per-database `res.users`; no global
identity table. **Session tokens HMAC'd with a per-database `database.secret`**
(`res_users.py:871-884`) — the strongest isolation primitive in the stack, and the reason SAAS-1
is a reachability finding rather than a data-read one. `list_dbs` scoped to role ownership
(`db.py:449`), so a second cluster on a different role is invisible. Correct session/DB rebinding
with forced logout when `dbfilter` rejects (`http.py:1844-1848`). The `odoo` role is correctly
**not** superuser.

**Other.** Vendored OCA has zero local drift. `odoo.conf` never committed. All manifest `data`
references resolve; all version strings well-formed. `.gitignore` is correct and well reasoned. No
outbound integrations exist, so pagination/retry/idempotency categories are empty by design.
