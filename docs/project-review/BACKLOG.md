# BACKLOG — single source of truth

Every finding appears here exactly once. All other documents reference these IDs.

- **Audit date** 2026-08-14 · **Commit** `962b30b9` · working tree clean apart from `docs/`
- **Calibration** production with real client data · **multi-company** · **multi-tenant SaaS planned**
- **Confidence** `CONFIRMED` (read the source or ran it) · `LIKELY` · `POSSIBLE` · `NEEDS_VERIFICATION`
- **Effort** XS <½d · S ½–1d · M 2–3d · L 1–2w · XL >2w

**Totals: 10 × P0 · 29 × P1 · 50 × P2 · 28 × P3 · 6 × P4 = 123 entries / 125 findings**

> **Recounted 2026-08-15.** This line previously read `9 × P0 · 24 × P1 · 31 × P2 · 18 × P3 · 6 × P4
> = 88 findings`, which was stale in every bucket but P4. Findings were appended by later passes
> without re-totalling, and resolved ones were marked in place rather than removed, so the figure
> drifted by 30. It is now counted from the document: `## <ID>` headings in P0/P1, table rows in
> P2–P4. **119 entries, 121 findings** — the two differ only because `DEP-3/4/5` is a single row
> covering three findings.
>
> **Re-recounted 2026-08-23**, and the drift repeated: the line above read `49 × P2 … = 122
> entries / 124 findings` because **TST-9** was appended to P2 on 2026-08-23 without re-totalling.
> That is the identical failure this note was written to record. The lesson is not "be careful" —
> it is that a total maintained by hand will drift. **Count it from the document; do not carry it
> forward.**
>
> The count includes entries already closed. **Do not read a hand-typed total here as current** —
> this line has now drifted three times, which is the whole point of the note above. As of
> 2026-08-30 the *derived* figures are **35 RESOLVED, 4 PARTIAL (CI-1, CI-2, DAT-1, TST-7), 82 OPEN**.
> Recover them from the document rather than from this sentence:
>
> ```bash
> venv\Scripts\python.exe tools\check_backlog_counts.py   # also runs in `lint`
> ```
>
> A grep pair was offered here first and was wrong: it returned 33 against a stated 31 + 3, because
> the status text uses three spellings for partial and the two shapes of entry need different
> patterns. That is the whole reason this is a tool and not a one-liner.
>
> The 2026-08-23 line claimed 27 resolved while the body already marked 31: **COD-2, TST-2 and
> TST-3** were resolved in place and never added here, and OPS-6 was listed as PARTIAL without a
> PARTIAL marker in its own entry. Corrected 2026-08-27, and stated as derived so the next
> correction is a re-run rather than a re-count.
>
> Three of those "resolved" entries carry a residual a reader should not mistake for closed:
> **FIN-1** is resolved as a *defect* (tags backfilled, test guards them) but its **go-live gate
> stays shut**, because a usable IRD filing needs the box layout, which is SME-gated and not in
> this repository. **UPG-1**'s design objection survives its fix. **TST-5**'s certificate layout
> is still an unconfirmed placeholder.
>
> **COD-11** was added 2026-08-17 while making the reports drillable: OCA's reports discard the
> drill-down domain they already compute and rebuild it in QWeb, which is the root cause behind the
> broken aged-balance drill-down (now repaired by overlay) and the two reports that have none.
>
> Three of the P2 entries are new from the wkhtmltopdf work: **DEP-6** (unmaintained PDF engine),
> **TST-8** (`date_range` tests error; **resolved 2026-08-19**, the suite is now green) and **OPS-7**
> (`run-odoo.ps1` documented a `--db` flag it never parsed; **resolved 2026-08-19**, both spellings
> now work). **BS-8** was rescoped in place — its
> original diagnosis was wrong, and the correction is stated in the row itself rather than silently
> applied.

> **This audit supersedes the first pass and corrects two of its conclusions.** Both corrections
> are stated explicitly at **FIN-1** and **FIN-2** rather than silently amended.

---

# P0 — Critical

## FIN-2 · Balance Sheet, P&L and Cash Flow cannot render
**RESOLVED 2026-08-15** · Accounting · `account_financial_statements/`

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

**Fix** ~~Rename the three `_name`s to `report.<report_name>`~~ — that direction does not work,
and the reason is worth recording. Odoo derives a table name from `_name` **even for an
AbstractModel** and validates its length, and
`report_account_financial_statements_report_balance_sheet_document` is **65 characters**, past
PostgreSQL's 63-character identifier limit. `-u` fails outright with
`ValidationError: Table name ... is too long`.

The two names are locked together, so the fix went the other way: the **templates** were renamed
`report_balance_sheet_document` → `balance_sheet` (and likewise for the other two), with
`report_name` and `report_file` following. The models keep their short, already-correct names.

Applied 2026-08-15, and the reports now render — verified through `_render_qweb_html`, which is the
call the audit used to prove they did not.

A second defect was found on the way: `_get_report_values` read `data['wizard_id']`
unconditionally. The wizard's buttons supply it, but a report opened by URL
(`/report/html/<report_name>/<id>`) arrives with empty `data` and would have raised `KeyError`
there even after the name mismatch was fixed — and that is the route the error page's own retry
link uses. The wizard is now recovered from `docids` when `data` is empty, and a genuinely missing
wizard raises a `UserError` that says what to do instead of a `KeyError` from inside QWeb.

**Tests** `TestReportsActuallyRender` renders all three by both routes and asserts the company name
reaches the template — the expression that raised `KeyError: 'wizard'`. It also asserts the
`report_name` → model-name link directly, which is cheaper to read than a render failure and names
the rule. **Effort S.**

## SAAS-2 · Live one-request cluster takeover via the database manager
**RESOLVED 2026-08-22.** The exploit was wholly conditional on
`verify_admin_password('admin')` returning True: while it did, any POST to a manager route
ran `change_admin_password("admin", master_pwd)` and adopted the attacker's value before
proceeding (`web/controllers/database.py:73-75`, and the same three lines in `duplicate`,
`drop`, `backup`, `restore`). The master password is now a 32-character random value
**stored hashed**, so that branch is unreachable. Verified: the literal `'admin'` no longer
verifies.

Note what did **not** fix it: `list_db = False`. That gates only the database *list*
(`odoo/service/db.py:49,435,484`). `/web/database/manager` is `auth="none"` with no
`list_db` guard at all (`web/controllers/database.py:65-69`) and still serves
create/drop/backup/restore forms, confirmed by fetching it. Password strength is the only
in-Odoo control; blocking the routes at the proxy is the deployment control, and
`deploy/README.md` now carries an nginx rule for it.
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

## SUP-2 · No git remote — 43 commits on one disk, never reviewed
**CONFIRMED** · Repository

`git remote -v` empty; single ref `refs/heads/main`; no tags, no merges, no PRs.

**Impact** Total loss of all work if the disk or `.git` is damaged — and per DAT-1 the sync
product standing in for a backup is itself the leading corruption risk, so it would replicate
damage rather than protect against it. Combined with CI-1, **no change has ever been reviewed or
verified.** **Fix** Create a remote and push. **Effort XS.**

**DEFERRED by decision 2026-08-30 — stays OPEN.** The remote belongs with the future production
deployment; the app runs on localhost until then. Recorded rather than left implicit, because a
deferral nobody wrote down is indistinguishable from an oversight six months later.

**The residual is now concentrated, not reduced.** DAT-1 moved the *data* out of cloud sync, which
leaves `.git` (340 MB) as the one irreplaceable thing still inside it — and per DAT-1 the sync client
is itself the leading corruption risk for a live `.git`, so it would replicate damage rather than
protect against it. 69 commits, still never reviewed.

**Mitigation applied, and it is not a substitute for a remote:** a `git bundle` written to
`C:\Users\i81129\odoo-backups`, outside the sync root alongside the database dumps. A bundle holds
every ref and object in one file, is checkable with `git bundle verify`, and can be cloned directly.
It converts "one copy" into "two copies on different paths". Deliberately a manual step rather than
an automated one — an unattended backup nobody has rehearsed restoring is its own kind of false
comfort. Re-make it after significant work:

```
git bundle create "C:\Users\i81129\odoo-backups\odoo19-repo.bundle" --all
git bundle verify "C:\Users\i81129\odoo-backups\odoo19-repo.bundle"
```

**Unblocked 2026-08-22.** This was held up by SEC-1: pushing would have published live
credentials. They are rotated, so it publishes nothing usable and the decision is now purely
about where the code should live. Private remains the sensible default for client work, but
it is no longer a security requirement.

## DAT-1 · Database dumps, filestore, live sessions and credentials in corporate cloud sync
**PARTLY RESOLVED 2026-08-27** · Data protection · local half done, cloud retention outstanding

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

**PARTLY RESOLVED 2026-08-27 — the local half is done; the cloud half cannot be done from here.**

`data_dir` moved out of the sync root to `C:\Users\i81129\odoo-data`, chosen because the profile
root is not a Known-Folder-Move target (`Desktop`, `Documents` and `Pictures` here are). What left
the sync root: the 596-file / 130,593,454-byte filestore (copied and byte-verified, with sha256 spot
checks on the five largest blobs, *before* the source was deleted), **154 session files** (purged,
not migrated — a session file is a bearer credential, so destroying them is the point), the two
`pg_dump` images (moved to `C:\Users\i81129\odoo-backups`, not deleted: they are the only
pre-migration rollback images), and nine stray hand-redirected logs. `.odoo_data` no longer exists.
Verified by reading attachment bytes back: **84 store-backed rows, 84 readable, 0 empty** —
identical to the pre-move baseline, which was measured first precisely so a pre-existing `b''` could
not be mistaken for damage. That is the technique the OPS-1 fix used.

**The ACL step was dropped as security theatre after measuring it.** `odoo.conf` already grants only
`NT AUTHORITY\SYSTEM`, `BUILTIN\Administrators` and `VERISK\I81129` — no broad groups. Stripping
SYSTEM and Administrators would break backup and AV and buy nothing, because the sync client runs
*as the user*: any user-readable file inside the sync root is replicated regardless of ACL. The ACL
was never the lever; removing the file from the root was.

**Residual, and why this is not RESOLVED.** Relocation stops *future* replication. It does not
retract what the tenant already holds — OneDrive cloud copies, version history and the recycle
bin / retention policy may still contain both dumps, the session files and `odoo.conf`. Purging that
is a OneDrive-web or Verisk-IT action. **The go-live gate stays shut until that is confirmed.**

Still in the sync root and out of scope for this pass: `.git` (340 MB, the *integrity* half of this
finding), `venv` (205 MB) and `.runtime` (119 MB). Moving the whole tree would close those too, but
it rewrites absolute paths in `odoo.conf`, both wrappers and the venv, and belongs in its own change.

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
**RESOLVED 2026-08-23.** The chart's tax data was re-applied for companies on the `np`
chart, via a `post-migration` in `l10n_np/migrations/19.0.1.1.0/` calling core's
`try_loading`. Repartition tag links went **0 to 16**.

16, not 24, is correct and worth recording: the two 13% taxes take a tag on all four
repartition lines (Base and Tax, invoice and refund), while the 0% and Exempt taxes take
one on their **base lines only** — a zero-rated supply has no tax amount to report. That
mirrors `account.tax-np.csv`, which leaves those cells empty.

Rehearsed on a `CREATE DATABASE ... TEMPLATE` copy before being run anywhere real, because
a chart reload is not obviously safe on a database with posted entries. Accounts, taxes,
fiscal positions, journal entries and journal items were all unchanged in number, and no
tax was renamed `[old]` or duplicated. The migration was then tested through the real `-u`
path on a second copy reset to the broken state, and `l10n_np` was bumped to 19.0.1.1.0 so
it fires at all — which also makes this module the first to satisfy **UPG-2**.

**What this does not do**, and the reason the go-live gate stays shut: it does not make the
VAT return produce a figure. There are **zero taxable journal items** in the database — all
eight posted documents have `amount_tax = 0.00` and no line carries a tax. So the return
moves from *nil because untagged* to *nil because nothing taxable exists*, and the two are
indistinguishable to a user. The remaining distance is the IRD form's boxes and their signs,
which are **not in this repository** and are SME-gated, plus representative taxed
transactions to check against (**SCH-2**).

**One sequencing trap**: `tax_tag_ids` is stamped at post time, so this repairs the taxes,
not history. Any entry posted while the tags were missing stays untagged and invisible to
the return; re-tagging means resetting it to draft and reposting. Moot here, given no posted
line carried a tax.
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
**RESOLVED 2026-08-23.** `test_box_from_tax_tags_ties_to_ledger` built its tax from whatever
the chart happened to provide, so when the chart provided no tags it called `skipTest` — and
excused itself under precisely the condition it existed to detect. It now builds its own tax,
tags and invoice as fixtures, which cannot be absent, and asserts an exact figure (226,000 =
base 200,000 plus tax 26,000, summed with sign -1) in place of `assertGreater(amount, 0)`,
which a wrong sign or a partial sum would have passed.

Whether the *chart* is wired is now a separate test, `test_chart_taxes_carry_repartition_tags`,
which is the one that actually guards FIN-1. Confirmed by watching it fail before the fix —
"VAT 13% (sale) has 4 of 4 repartition lines with no tax tag" — and pass after. The module's
computation was correct all along; only the data was broken, and separating the two tests is
what makes that visible.
**CONFIRMED (skip fires today)** · Testing · `l10n_np_vat_return/tests/test_vat_return.py:81-83`

`if not tags: self.skipTest("sale tax has no tax tags configured in this chart")`. "No tags" is
not a precondition — it *is* the defect. Evaluated live: `VAT 13%`, `tags=0`, **skip fires**.

**Impact** The module reports green while never proving a box ties to the ledger. **Fix** Build
tax, tags and invoice as fixtures; assert exact box values; the test must not be able to skip.
**Effort S.**

## ACC-1 · Loans post foreign-currency amounts as company currency
**RESOLVED 2026-08-30** · Accounting · `l10n_np_loan/models/loan.py:286-297, 371-396`

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

**RESOLVED 2026-08-30** — the hole is closed, not papered over. `currency_id` is now
`related='company_id.currency_id'`, stored and readonly, and the form field under
`base.group_multi_currency` is gone. The figure the schedule rounds in is now, by construction, the
figure the move lines are denominated in.

The three `column_invisible` occurrences stay: the Monetary widgets need the field present in the
view to render. `tests/test_multi_company.py` had to stop passing `currency_id` into `create()` —
against a readonly related field that write's inverse target is the company's own currency.

**Real multi-currency was deliberately not attempted.** It is a feature — `amount_currency` on every
line, a rate on every posting date, revaluation at period end — not a bug fix. It is also not a
bookkeeping toggle in Nepal, where foreign-currency borrowing requires Nepal Rastra Bank approval,
so it should not be reachable from a checkbox on a loan form. If it is ever needed it becomes an SME
sign-off item in its own right.

Safe without a migration, verified rather than assumed: the database held **0 loan records**, one
company, currency NPR, so nothing could be re-denominated by the change. Three tests added, of which
the load-bearing one asserts that `create()` handed a *different* currency still yields a loan in the
company's. Note that `test_drawdown_entry_is_balanced_and_hits_the_liability` passed throughout the
defect — balance is preserved by it, because both sides were wrong by the same amount, which is why
the new tests assert denomination rather than arithmetic.

## ACC-2 · Balance Sheet omits prior-year unallocated earnings
**RESOLVED 2026-08-23.** The balance sheet now carries an **Unallocated Earnings (prior
years)** line in the equity section, computed as P&L *since inception* minus the current
fiscal year, and added to Total Equity alongside the current result.

Confirmed as **LIKELY → CONFIRMED** before fixing, by watching the new test fail against the
old arithmetic: a single 50,000 expense dated in the previous fiscal year produced
`Balance sheet out by -50000.0`. Verified again on the live database afterwards — the same
entry leaves `difference = 0.0`, puts 50,000 into unallocated, and leaves the current
result untouched at 170.0.

Computed as *since inception minus current year* rather than by summing a date-bounded
section, so it cannot disagree with the Current Period Result printed beside it: both come
from `_period_result`, and together they are the full history by construction.

The two figures are kept as **separate lines** deliberately. Combining them would also
balance, and would misstate this year's profit on the face of a statutory statement — an
accountant reads "this year" and "everything before it" as different things. One of the four
tests asserts exactly that: a prior-year entry must move `unallocated` and must **not** move
`result`.

Three details worth keeping:

- The line renders **only when non-zero**. On a first-year sheet it would always read zero,
  and a permanent zero row teaches the reader to stop looking at it.
- `_unallocated_earnings_domain` uses `date < fy_date_from`, not `<=`. An entry posted on the
  first day of the fiscal year belongs to this year's result; off by one and a full day's
  trading silently becomes history. A test sits on that boundary, because no fixture that
  avoids it would ever catch this.
- The drill-down's `balance` sum is the **negation** of the printed figure, as for the
  current result, and a test ties the two together.

*Original finding, for context:* · `financial_statements.py:146-149`

Assets and liabilities are cumulative since inception (`:139`, no lower bound), but the result
added back covers only the **current** fiscal year. Community posts no automatic year-end close,
so income and expense accumulate across years.

**Impact** `difference = Σ(prior years' P&L)`. After year one the sheet does not balance and a
"difference" line appears on a statutory statement. `test_balance_sheet_balances` posts only
current-FY entries, so it passes.

**Fix** Add an *Unallocated Earnings* line = P&L since inception − current year; test with a
prior-FY entry. **Effort S.**

## ACC-3 · Export fiscal position performs no tax substitution
**RESOLVED 2026-08-23.** `original_tax_ids` now links each zero-rated NP tax to the 13% tax
it replaces, in the template (for fresh chart adoptions) and by a `post-migration` in
`l10n_np/migrations/19.0.1.2.0/` (for databases already on the chart). Substitution links
went **0 to 2**. Verified end to end on the live database: an export invoice comes out
`VAT 0% / tax=0.00 / total=1000.00`, a domestic invoice still `VAT 13% / tax=130.00`.

**The audit's fix was right, and my plan's elaboration of it was not.** The finding said
"one cell each"; the plan claimed a second, independent cause — an unset
`company.domestic_fiscal_position_id` leaving `is_domestic` False — and cited
`account_tax.py:5160` as the gate. A negative control disproved it: with the link present
but `domestic_fiscal_position_id` cleared and `is_domestic` False, an export invoice still
came out at 0%; clearing the link instead put 13% straight back. `:5160` is in
`_import_retrieve_tax_from_price_include_exclude`, a bill-import matching helper, and its
`is_domestic` is the one on **`account.fiscal.position`** (`partner.py:58`) — a different
model on a different code path. Every real use of `account.tax.is_domestic` is UI-side:
the `original_tax_ids` domain (`:110`), the `name_search` "Domestic" filter (`:262`), and
two list-view filters. Two line numbers that look alike are not the same gate.

`domestic_fiscal_position_id` is still set by the migration, for a smaller and honest
reason: without it the `Replaces` field's own domain `[('is_domestic','=',True)]` matches
nothing, so an accountant opening VAT 0% gets an empty dropdown and cannot maintain — or
even see — a link the migration wrote by ORM, where domains go unenforced.

**`try_loading` cannot deliver this**, unlike FIN-1 next door, and the migration's own
assertion is what caught the first attempt failing with the table still empty.
`chart_template.py:412-421` re-applies `original_tax_ids` only `if force_create and
original_tax_ids and (new_taxes := [xml_id for ... if xml_id not in xmlid2tax])` —
comment: *"Only add tax mappings containing new taxes"*. `VAT_S_NP_13` already exists, so
core deliberately declines to touch the mapping; it treats substitution links on existing
taxes as user-managed. A reload re-applies repartition tags and fiscal-position links, and
nothing else. So the migration writes the link directly, by xmlid.

**Not retrospective.** Taxes resolve when an invoice line is created, so any export
already billed at 13% stays wrong and needs a credit note. Same shape as FIN-1's post-time
stamping. Moot here: no such invoice exists yet.

Rehearsed on a `CREATE DATABASE ... TEMPLATE odoo19` copy before running anywhere real,
then dropped. Accounts (47), taxes (6), fiscal positions (2), journal entries (10) and
journal items (24) unchanged throughout.

**CONFIRMED** · Accounting · `l10n_np/data/template/account.tax-np.csv:10,14`

Odoo 19 expresses substitution through `account.tax.original_tax_ids`
(`odoo/addons/account/models/account_tax.py:102-114`). Both zero-rated NP taxes leave that column
**empty**. Upstream contrast: every non-domestic `l10n_uk` tax names the domestic taxes it
replaces.

**Impact** Applying the Export position leaves VAT 13% on the line — exports invoiced at 13%,
over-collection, wrong VAT return. **Fix** One cell each: `VAT_S_NP_13` / `VAT_P_NP_13`. Same
migration caveat as FIN-1. **Effort XS + migration.**

## UPG-1 · Local module overwrites core `account.*` group records
**RESOLVED 2026-08-23 by measurement and a guard test, not by the prescribed refactor —
because the stated impact does not happen.**

`-u` propagates to every module that depends on the named one, and dependents always load
*after* their dependencies. So `-u account` reloads `account` (64/153) **and**
`l10n_np_accounting` (119/153) in the same transaction: upstream resets the records and this
module immediately re-applies them. Three consecutive `-u account` runs on a probe left
`name`, `privilege_id`, `sequence` and `implied_ids` byte-identical.

Two details also narrow the claim. Upstream declares only `name` and `implied_ids` on these
records, so `privilege_id`, `sequence` and `comment` were never at risk. And upstream's
`implied_ids` uses `(4, ref(...))`, which **links** rather than replaces, so the
manager-implies-accountant edge would have survived a reload on its own.

**The prescribed fix would have been worse.** A `post_init_hook` runs on *install only*, so it
would not re-run during `-u account` — it would introduce exactly the fragility the current
arrangement avoids, by accident of dependency ordering. Five tests now assert the invariant
instead (`test_account_group_wiring.py`), including reachability of the Accounting and
Reporting menus through `_visible_menu_ids()`, so if a future Odoo changes how reloads or
propagation work, the suite says so rather than a user finding the menu gone.

What remains valid is the **design objection**, which no test fixes: these are records owned by
another module, so uninstalling this one leaves them changed. `account_groups.xml` says so in
its own header.

**CONFIRMED** · Upgrade safety · `l10n_np_accounting/security/account_groups.xml:32,39,49`

`<record id="account.group_account_readonly">` and two siblings rewrite records **owned by
`account`**, and they are not `noupdate`.

**Impact** Any `-u account` — including every 19.0.x point release — reloads them from upstream
XML, dropping `privilege_id`, `sequence`, the renames and the manager⇒user implication. The
Accounting / Review / Reporting menus silently vanish again. Uninstalling the module does **not**
revert them either. This is core modification wearing a data costume.

**Fix** Move to an idempotent `post_init_hook`; add a test asserting the implication holds, run
after `-u account`. **Effort S.**

## BS-20 · List views bypassed the whole Bikram Sambat layer
**RESOLVED 2026-08-15** · Bikram Sambat · `nepali_calendar_core/static/src/registry_overrides.js`;
`web/static/src/views/list/list_renderer.xml:299`; `web/static/src/views/utils.js:139-151`

With the calendar set to BS, invoice and bill **list** columns still rendered Gregorian
(`Aug 14`, `5 days ago`) while the same fields rendered BS in the form view.

Odoo 19 renders a date by two routes. A readonly list cell takes the one that instantiates **no
component at all**: `canUseFormatter` (`list_renderer.js:501-511`) is true for any column without an
explicit `widget=`, and the cell is then plain text from the **`formatters`** registry. The module
overrode only the `fields` registry, so the dispatcher was never reached. Kanban
(`kanban_record.js:216-219`) had the identical defect.

The module's own comment asserted the `formatters` registry served only aggregates and carried no
field metadata. Both halves were wrong, and that premise is why the gap existed.

Separately, the **Due Date** column is `widget="remaining_days"`
(`account/views/account_move_views.xml:536`), whose component imports `formatDate` statically
(`remaining_days_field.js:9,61`) and is reachable by neither registry.

**Impact** The headline feature was absent from the highest-traffic surface in an accounting system.
It presented as an inconsistency rather than a failure, so it read as "partly implemented".

**Fix** Applied. `formatters` `date`/`datetime` overridden — one place, covering list cells, kanban
and aggregates — plus a narrow patch of the two `remaining_days` getters. Timezone rule preserved:
datetimes are re-zoned to `user.tz` before the BS day is taken, plain dates are not. Exclusions on
the formatter route are by field name only, because that call site has no model; documented in
[`BIKRAM_SAMBAT.md`](BIKRAM_SAMBAT.md). **Effort S.**

**Why it shipped** The only list-view test asserted `expect(".o_data_row").toHaveCount(1)` and
nothing about rendered text, so it stayed green throughout. Eleven tests now assert the rendered
value on that path, including that **no component is mounted** — which pins the fix to the route it
was written for.

## BS-21 · Pivot cells and the calendar popover remain Gregorian
**CONFIRMED** · Bikram Sambat · `web/static/src/views/pivot/pivot_renderer.js:90`;
`web/static/src/views/calendar/calendar_common/calendar_common_popover.js:71`

Both carry a private `getFormattedValue` that does not consult the `formatters` registry, so they
are unaffected by the BS-20 fix.

**Impact** Low and bounded. Pivot date *cells* are rare — pivot's real BS problem is group-by bucket
boundaries, which is BSF-3 and a much larger piece of work. The calendar popover shows a date the
user just clicked on.

**Fix** Patch each if it becomes visible in practice; not worth two more patched core methods
otherwise. **Effort XS. P4.**

## BS-1 · The exhaustive Python↔JS cross-check is dead code
**RESOLVED — and it was already resolved when this entry was written up as open.** Settled
2026-08-23 by execution: `nepali_calendar_core/tests/test_conversion_contract.py:50,78` calls
`selftest.check()`, once in full and once sampled. It is wired, it runs in the suite, and
`docs/bs-calendar/BACKLOG.md` (BSC-10, "Done") was the correct record all along.

> **Root cause of this and every other stale BS entry.** Commit `c7a73ae8` moved the Bikram
> Sambat implementation out of `l10n_np_bs` into `nepali_calendar_core`. Every BS finding below
> still cites the **old** paths — `l10n_np_bs/tools/selftest.py`, `l10n_np_bs/static/src/…` —
> which no longer exist. `l10n_np_bs` now holds a manifest, a README and a documented
> compatibility shim. The findings read as open because nobody re-pointed them at the new module,
> not because the defects survived. `docs/bs-calendar/BACKLOG.md` was maintained alongside the
> move and is the more reliable record for anything BS.
>
> This is worth more than the individual corrections: **a finding that names a path is only as
> current as that path.** Four separate entries were wrong for one reason.

*Original finding, for context:* · `l10n_np_bs/tools/selftest.py`

`selftest.py` performs exactly the 46,022-day sweep that proves the generated JS table matches
Python. It is not imported by `tests/__init__.py`, not called anywhere, and referenced only in
its own docstring and the manifest prose. `l10n_np_bs/__init__.py` is empty.

**Impact** The manifest's central safety claim — *"the Python and JS sides can never drift
apart"* — is enforced by a script nobody runs. Bumping `nepali_datetime` or hand-editing the
"DO NOT EDIT BY HAND" table would not be caught. **Fix** Wire it into the test suite. Highest
value per unit effort in the whole backlog. **Effort S.**

## BS-2 · `datetime` declared supported with zero timezone normalisation
**RESOLVED.** Settled 2026-08-23 by reading the current source:
`nepali_calendar_core/static/src/bs_date_field.js:64-77` re-zones to `user.tz` for datetime
fields, with a comment recording exactly why — `.setZone("default")` resolves to the *browser*
zone because Odoo never assigns `luxon.Settings.defaultZone` in production. Lines 129 and 185 use
`user.tz` for "today" as well.

It is also **tested**, which the finding asked for: `tests/test_timezone_and_reports.py` pins the
UTC+05:45 boundary — 18:30 UTC is 00:15 the next day in Kathmandu, so the BS date must not shift
into the reader's zone. See the module-move note under **BS-1**.

*Original finding, for context:* · `l10n_np_bs/static/src/bs_date_field.js:44-55, 205`

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
**RESOLVED 2026-08-22.** Both rotated; `RECONNAISSANCE.md` redacted at the four sites that
carried values, with a note at the top saying why. The master password is now stored hashed
in `odoo.conf`, so it is in plaintext nowhere.

**History deliberately not rewritten.** The leaked values were `admin` and `odoo` —
well-known defaults rather than secrets — and after rotation they open nothing. Rewriting 41
commits to purge strings that are already worthless was judged not worth changing every SHA
for. Anyone reading old commits will still see credentials and may reasonably raise it
again; this paragraph is the answer.

A redaction trap worth recording: the database password was the literal string `odoo`, which
occurs **109 times** in that document as the product name, the package directory and
`odoo.conf`. A global find-and-replace would have destroyed the file. The four real leak
sites were edited individually.
**CONFIRMED** · Security · `RECONNAISSANCE.md:232,236,480`, commit `e4ff7dab`

The document reproduces the effective config verbatim, including the **current** values — and
flags them as critical while being the vehicle that publishes them. **Rotation is unavoidable**;
they are in immutable history. Compounds SAAS-2. **Effort S** (rotate) / **M** (history).

## SEC-2 · No record rules on any locally written model
**RESOLVED 2026-08-23.** Ten global `ir.rule` records now scope every locally written
company-owned model: two in `l10n_np_loan`, four in `l10n_np_tds`, four in
`l10n_np_vat_return`.

**Proved by negative control, not by inspection.** With the ten rules disabled — which is
the state this repo was in before today — a company A accounting *manager* could read
company B's VAT return form, its boxes, the filed return, its individual figures and a TDS
certificate. Every one came back readable. With the rules active, every one is refused. The
leak was real and these rules are what closes it.

**Two corrections to the finding, both of which changed the work:**

- *"10 models across 6 modules"* is **3 modules**, not 6. The other three local modules
  define no company-owned persistent model: `l10n_np` has only an `AbstractModel`,
  `l10n_np_fiscal_year` and `l10n_np_accounting` only `TransientModel`s and extensions of
  core models, which core's own rules already cover. Transient records need no rule.
- *"every new model carries `company_id`"* was **not true** of two of them.
  `l10n_np.vat.return.box` and `l10n_np.vat.return.line` had no such field, so there was
  nothing for a rule to filter on and the prescribed fix could not have been applied as
  written. Each now carries a stored `related` `company_id` — from the owning form version
  and filed return respectively — mirroring `l10n_np.loan.line` and
  `l10n_np.tds.certificate.line`, which already did this.

**Deliberate deviation from the prescribed domain.** The finding suggests
`['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`. The `False` branch
is omitted: `company_id` is `required=True` on all ten models, so an unowned row cannot be
created through the ORM and the branch is dead code. It is also the wrong default to leave
lying around — were the field ever made optional, that branch would silently expose an
unowned filed return to every company. Strict beats defensive here.

Core's `parent_of` operator was likewise **not** used, including on the arguably shareable
master data (`l10n_np.tds.category`, `l10n_np.vat.return.form`), which are statutory rates
and form layouts a company group might reasonably share. Whether they should be shared down
a hierarchy is a business decision about group structure and needs an SME; over-sharing is
the failure mode SEC-2 exists to close, so the strict rule is what shipped, and the two
rule files say so.

The rule files are deliberately **not `noupdate`**, unlike the OCA file they were modelled
on. A rule frozen at install cannot be corrected by an upgrade, and stale security surviving
a code change is precisely the hazard **UPG-1** and **UPG-2** already record here. All three
module versions were bumped so `-u` actually applies them.

Fifteen tests across the three modules, all using `with_user` with a real non-superuser —
`TransactionCase.env` is the superuser, and record rules never apply to it, so a check run
as `self.env.user` would have passed with no rules installed at all. `with_company` alone
would not do either: it changes which company is *active*, while the rule filters on
`company_ids`, which comes from which companies the user is *allowed*. Each module also
asserts its own records stay fully readable and writable, which is what stops a rule of
`[(0, '=', 1)]` from passing everything else.

Still open and adjacent: **SEC-6** (the read-only role can rewrite a return line — an ACL,
not a rule) and **SCH-1** (`company_id` is now the hot column on every one of these queries
and is still unindexed).

**CONFIRMED** · Security · 10 models across 3 modules

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

## CI-1 · No CI of any kind — 304 tests, and only a manual runner
**PARTIALLY RESOLVED 2026-08-15** · Build

No `.github/`, `.gitlab-ci.yml`, `Jenkinsfile`, `tox.ini`, `pytest.ini`, pre-commit or Makefile.
Neither launcher passes `--test-enable`. There is no single command that runs all eight suites.

**Impact** Verification theatre. Four consecutive commits (`b2570489`, `d9b0bc4a`, `fcb814f3`,
`cb96ff96`) are same-day fixes for defects a test run would have caught. **Effort M.**

### The reporting half is fixed too (2026-08-23); automation still is not

`test` now reports the **skip count** and names every skipped test, with
`-FailOnSkip` / `--fail-on-skip` to exit non-zero for CI. That closes the half of this
finding that TST-3 depended on: Odoo tracks `result.skipped` internally and never prints
it, so its summary line reports only `N failed, M error(s) of K tests`
(`odoo/tests/result.py:198`) and a run that skipped everything is indistinguishable from
one that passed everything. Verified against a deliberately skipped test: Odoo said
"0 failed, 0 error(s) of 9 tests" while the launcher said "Skipped: 1" and named it.

`lint` was added alongside, running ruff, pylint-odoo and the manifest-version check.

**What is still missing is the automation itself.** There is no runner invoking any of this
on a push, and with no git remote (SUP-2) there is nothing to push to. Both halves of that
are one decision away.

### The runner half was fixed earlier

There is now a single command:

```
.
un-odoo.ps1 test -Db <database>          # every custom module suite
.
un-odoo.ps1 test-module <module> -Db <database>
```

`run-odoo.sh` takes the same verbs. It passes `-u <modules> --test-enable --test-tags /<mod>,...` —
both halves are required, because `--test-enable` alone runs nothing for modules already up to date —
and it **propagates Odoo's exit code unchanged**, so a failing suite cannot be mistaken for a pass. It
demands an explicit database, because `-u` modifies the named one. `-Db <name>` is the PowerShell form
and `--db <name>` the shell one, but since 2026-08-19 either works on either script (**OPS-7**,
resolved).

**Still open: nothing runs it automatically.** There is no CI, and this repository still has no remote
to run one against (**SUP-2**). The command existing is a precondition for CI, not a substitute for it.
Remaining effort **M**.

## DEP-1 · `nepali_datetime` undeclared — a clean build cannot install the suite
**RESOLVED** · Dependencies · was `l10n_np_bs/__manifest__.py:36`, now `nepali_calendar_core`

Declared in `external_dependencies`, which pip never reads; absent from `requirements.txt`;
present in the venv only because it was installed by hand; unpinned.

**Impact** `l10n_np_bs` refuses to install on a fresh machine, and the umbrella depends on it, so
**the entire suite is uninstallable**. Blocks CI, DR restore and any second developer.
**Effort XS.**

**Fixed.** `nepali-datetime==1.0.8.5` pinned in a marked project-additions block at the end of
`requirements.txt` — appended rather than merged alphabetically, so the stock-Odoo section stays
byte-identical and refreshing it from a newer Odoo release remains a readable diff. `polib==1.1.1`
is pinned in the same block.

> **One residual, found 2026-08-23 while reconciling these documents: `websocket-client` is still
> undeclared**, and three test files import it — `nepali_calendar_core/tests/test_calendar_ui.py`,
> `tests/test_js_unit.py` and `account_reports_interactive/tests/test_js_unit.py`. It is present in
> this venv by accident of Odoo's own requirements, so the tests pass here and would fail on a
> clean build of the kind this finding exists to protect. **Effort XS**, and it belongs in the same
> project-additions block.
`nepali_calendar_core/tests/test_requirements.py` fails if the pin is dropped by such a refresh,
drifts from the installed version, or is loosened to `>=`; the guard was verified by removing the line
and confirming the suite goes red. `deploy/README.md` no longer carries a separate unpinned
`pip install`. **COD-10 is narrowed but not closed:** the private `_days_in_month` is still private,
and there is now a test asserting it exists.

## OPS-6 · Unbounded logs: Odoo has no rotation, and nothing supplied it
**CONFIRMED (by inspection)** · Operations · `odoo/netsvc.py:260-275`; `odoo.conf`;
`deploy/odoo.conf.linux.example:58-62`

Odoo ships **no size-based rotation at any point** — an exhaustive read of `netsvc.py` finds
`WatchedFileHandler` (POSIX) and `logging.FileHandler` (Windows), never a `RotatingFileHandler`. Both
only ever append.

Compounding it, the dev `odoo.conf` sets **no `logfile` at all**, so a hand-started server logs to
stderr and the output is lost unless the caller redirects it. That is why `.odoo_data/` accumulated nine
hand-redirected files (`server.log`, `srv.out`, `tests.log`, `ne_boot.log`, …): log capture was unowned.
`deploy/odoo.conf.linux.example:62` advised adding logrotate but no configuration was ever shipped, and
`/var/log/odoo` is created by `deploy/README.md:46` and then never written to.

**Impact** A long-lived instance with `logfile` set fills its disk, which takes PostgreSQL and the
filestore down with it. Recorded before only as an unnumbered table row,
`PRODUCTION_READINESS.md:110`: "Logs | stdout → journald. No aggregation, retention or rotation".

**Fix** Applied 2026-08-15. `run-odoo.ps1`/`run-odoo.sh` pass `--logfile logs/odoo.log`, so the log has
an owner. `deploy/logrotate.d/odoo` ships the rotation config, with a note explaining why
`copytruncate` is **wrong** here (POSIX Odoo reopens on rename; copytruncate loses lines). Windows
cannot rename an open file and gets no `WatchedFileHandler`, so the script rotates at **start**, above
`ODOO_LOG_MAX_MB`, keeping `ODOO_LOG_KEEP` generations.

**Still open** journald's own `SystemMaxUse` is unset, and nothing aggregates or ships logs anywhere.
**Effort XS** (done) **+ S** (retention policy). 

---

## TST-2 · Five suites assert on live database state
**RESOLVED 2026-08-23** for the three that mattered — the ones asserting the database is
**empty**, which would have failed permanently the day an accountant did their job.

`test_ships_with_no_rates` and `test_ships_with_no_form` asked
`search_count([]) == 0`, i.e. "does the database contain any TDS rate / IRD form?". The
question they meant to ask is "does **this module ship** one?", and the two diverge the
moment the module is used for its purpose. They now count `ir.model.data` rows owned by the
module, which an accountant's records — having no xmlid — cannot affect.

`test_is_configured_flag` called `_is_configured()` with no argument, which answers for
`env.company`, and asserted False. It now creates its own company, where the assertion is
true by construction rather than by accident, and additionally asserts that configuring one
company does **not** mark another as configured — a property the old test could not see.

Demonstrated rather than argued. With one real TDS rate and one real IRD form in the
database, the old assertions evaluate to FAIL and the new ones to PASS; `_is_configured`
returns True for the live company and False for a fresh one. Rolled back afterwards.

**Why this was worth doing before the SME work, not after:** the IRD form layout is the
single most important thing anyone will ever enter here, and it is what unblocks the FIN-1
go-live gate. The old test would have turned that success into a red suite. A test that
fails when the system starts working gets deleted, and the assertion it was making goes with
it.

The remaining two suites in this finding assert on live state without asserting emptiness,
so they degrade rather than break. Left as-is; the fixture pattern to copy is
`l10n_np_fiscal_year/tests/test_np_fiscal_year.py:20-26`.

*Original finding, for context:*; three break when the modules are used
**CONFIRMED** · Testing

`test_ships_with_no_form`, `test_ships_with_no_rates` and `test_is_configured_flag` assert
`search_count([]) == 0` — a property of the **database**, not the module. They fail permanently
once an accountant configures TDS rates or an IRD form.

The correct pattern exists at `test_np_fiscal_year.py:20-26` (creates its own company, after this
exact bug bit in `82f3ee43`) and was never propagated. **Effort M.**

**A sixth instance surfaced on 2026-08-15, and it bit.**
`account_financial_statements`'s `test_profit_and_loss_arithmetic` posted one 400,000 invoice and
asserted `income.total == 400000.0` — but the P&L sums every posted line for the company in the
period, so the assertion silently depended on the books being empty of other income. It began
failing with `400150.0 != 400000.0` once real invoices existed, i.e. as soon as somebody used the
application.

Fixed by measuring the figures **before and after** and asserting the delta, plus the two identities
(`gross = income - cost_of_sales`, `net = gross - expenses`) on the absolute values, which hold
whatever else the books contain. That keeps the real subject of the test — the arithmetic — and
makes it independent of the database. Worth preferring to a throwaway company here: it is shorter,
and it also exercises the figures a user would actually see.

## TST-5 · The only path producing real TDS figures is untested and fails silently
**RESOLVED 2026-08-23**, and the finding understated it. `action_collect_lines` was not
merely untested and liable to report zero: **it could not run at all**, and it blamed the
wrong thing when it failed.

It searched `account.withholding.line`, which is an **AbstractModel**
(`l10n_account_withholding_tax/models/account_withholding_line.py:10`, `_auto = False`) with
no table. Verified by execution: `search()` on it raises
`UndefinedTable: relation "account_withholding_line" does not exist`. The bare
`except Exception` around the search then reported that as *"Check that
'l10n_account_withholding_tax' is installed"* — about a module that **is** installed. So
the feature had never worked, and its error message sent the user to look in the wrong
place. Being untested is why nobody knew.

Three more consequences of duck-typing against a schema that was never checked:

- **`partner_id` does not exist** on a withholding line; the payee is
  `payment_id.partner_id`. So `'partner_id' in l._fields` was always False, the payee
  filter degraded to `True`, and a certificate for one payee would have carried **every**
  payee's withholding. That is a disclosure of a third party's tax affairs on a document
  handed to someone else, not just a wrong total. It is the most serious thing in this
  finding and the finding does not mention it.
- **`date` does not exist either**, and `comodel_date` is computed and unstored, so it
  cannot appear in a domain at all. Every line would have been stamped with the period end
  rather than the payment date.
- `base_amount` and `amount` *do* exist, so those two `getattr(..., 0.0)` defaults never
  actually fired. The named failure mode was real but latent. Both are read directly now.

Now queries `account.payment.withholding.line` — the persistent subclass — filtered by
company, by `payment_id.partner_id`, by `payment_id.date`, and by
`payment_id.state in ('in_process', 'paid')`. That last filter is new and statutory: a
draft or cancelled payment has withheld nothing, and a certificate claiming otherwise
overstates the credit the payee may claim from the IRD.

**Eight tests**, every one through a real posted payment carrying a real withholding line
(base 100,000 → 10,000 withheld), never a hand-made certificate line. A test that built
the lines itself would only prove the certificate can add up, which was never in doubt, and
would have stayed green through everything above — the same error as FIN-2's statement
tests. They cover: the amount actually withheld; another payee's withholding **not**
appearing; the payment date rather than the period end; the sequence number being cited; a
draft payment excluded; a payment outside the period excluded; collecting twice not
doubling; and issuing before collecting refused.

The fixture builds its own company. Writes to `res.company` flush through `cr.precommit`,
so configuring `withholding_tax_base_account_id` on the real company would outlive the
suite. A chartless company supplies no tax group, no fiscal country, no outstanding
account and no partner payable, so all of it is built by hand — which is the honest cost of
not touching live configuration.

**Still a placeholder layout.** This fixes the figures, not the form: the certificate
layout remains unconfirmed by an accountant, and `category_id` on the collected line is
still unset (the tax-to-category mapping exists on `l10n_np.tds.category.tax_id` and could
drive it). Neither blocks the figures being right.

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
**RESOLVED 2026-08-22.** `admin_passwd` rotated and hashed, `list_db = False`. `doctor` now
reports `admin_passwd is not one of the known default values` where it used to warn.
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

**RESOLVED 2026-08-23.** `ruff.toml`, `.pylintrc` and `requirements-dev.txt` are committed,
and `run-odoo.ps1 lint` / `run-odoo.sh lint` run them. Both are **clean**: ruff went from
204 findings to 0, pylint-odoo to 0.

The findings it produced were worth having, and three were real defects rather than style:

* a **duplicate dictionary key** in `l10n_ne/translations.py` — `"Order"` mapped twice, so
  Python silently kept the second and the first was dead. Removed without changing runtime
  behaviour; which sense belongs where is an SME question a flat source-string dict cannot
  express.
* the two `assertRaises(Exception)` sites of **COD-7**, now asserting
  `psycopg2.errors.CheckViolation` — the actual exception, determined by running it.
* five modules with no README and several redundant `string=` field labels.

It also earned its place immediately, on my own work: renaming a lambda variable in
`account_move_line.py` I left one reference behind, and `py_compile` passed because a stale
name is a runtime `NameError`, not a syntax error. Ruff reported it as **F821 Undefined
name**. Confirmed deliberately afterwards by reintroducing the break and watching ruff catch
it.

One configuration lesson is recorded in `ruff.toml` itself: **isort must not touch an Odoo
`__init__.py`**, because import order there is semantic. Sorting them alphabetically inverted
`l10n_np_accounting/__init__.py`, whose own comment reads "`wizard` first: models/ extends
account.lock.dates, which is defined in wizard/, and an extension cannot precede its model" —
leaving the comment describing the opposite of the code. Caught by reading the diff. An
autofix is not safe merely because it is mechanical.

---

# P2 — Medium

| ID | Conf. | Area | Location | Problem | Impact | Fix | Eff |
|---|---|---|---|---|---|---|---|
| **SAAS-10** | CONFIRMED | SaaS | `web/controllers/database.py:41-42,65` | `/web/database/manager` **renders publicly even with `list_db=False`** — no route-level guard; falls back to `[request.db]` | Leaks server version, language/country lists, `insecure` flag, current DB name; serves a public master-password form | Block `/web/database/` at nginx | XS |
| **SAAS-11** | CONFIRMED | SaaS | `odoo/http.py:418` | `dbfilter` uses `.match()`, not `.fullmatch()` | `^%d` matches `acme_staging`, `acme_backup` | Always anchor `^…$` | XS |
| **SAAS-12** | CONFIRMED | SaaS | `odoo/http.py:1099-1119` | Cross-tenant session-**existence** oracle via `get_missing_session_identifiers` | Confirmation channel for SAAS-5 | Per-tenant session dirs | M |
| **SAAS-13** | LIKELY | SaaS | `web/controllers/binary.py:99-102,142` | `/web/assets/**any**/…` bypasses the version check; no `Vary` on Host | Behind a shared CDN keyed on path, tenant A's bundle could be served to tenant B | Key cache on Host, or no shared CDN | S |
| **SAAS-14** | CONFIRMED | SaaS | `odoo/http.py:1069-1075` | Session vacuum is cluster-wide with one `SESSION_LIFETIME` | Per-tenant session policy impossible at the store | Accept, or separate instances | — |
| **PG-1** | CONFIRMED — **NOT OURS TO FIX** (scoped 2026-08-23) | PostgreSQL | live cluster | The `odoo` role **can connect** to an unrelated 12 GB corporate database (`ist_datahub`) and enumerate 52 table names — but **cannot read any** (0 selectable, no CREATE) | Metadata exposure; widens the blast radius of an Odoo compromise | **Do not run the revoke from this project.** `REVOKE CONNECT ON DATABASE ist_datahub FROM PUBLIC` alters a **third-party corporate database**, and anything else connecting there on `PUBLIC` would break. `ist_datahub` remains at `datacl = NULL`, PostgreSQL's untouched default — verified. Owner's action, or accept it, or move Odoo off this cluster | — |
| **PG-2** | **RESOLVED 2026-08-30** — `REVOKE CONNECT ON DATABASE odoo19 FROM PUBLIC`. `datacl` was NULL, so the built-in default applied and every role on the cluster could connect; it now reads `{=T/odoo,odoo=CTc/odoo}` and `has_database_privilege('public', …, 'CONNECT')` is false. PUBLIC retains TEMP, which is unreachable without CONNECT. Repeatable via `tools/harden_database.py`, asserted by `test_database_hardening.py` | PostgreSQL | `datacl = NULL` on all DBs | New databases default to `PUBLIC CONNECT` | Harmless with one role; wrong the moment a reporting/metrics role exists | Revoke in provisioning | XS |
| **PG-3** | CONFIRMED | PostgreSQL | shared catalogs | From one tenant's connection, `pg_database`, `pg_roles`, `pg_stat_activity` enumerate all tenants | Tenant enumeration; other tenants' query strings visible in `pg_stat_activity` | `pg_stat_statements` restrictions; accept enumeration | S |
| **PG-4** | **RESOLVED 2026-08-30** — `REVOKE CREATE ON SCHEMA public FROM PUBLIC`. `nspacl` went from `=UC/pg_database_owner` to `=U/pg_database_owner`, i.e. PUBLIC keeps USAGE and loses CREATE. **This one comes back**: Odoo re-grants it on every database it creates (`odoo/service/db.py:168-174`), so `tools/harden_database.py` must run after each `createdb` — which is what 'revoke in provisioning' means. Asserted by `test_database_hardening.py` | PostgreSQL | `odoo/service/db.py:168-174` | `GRANT CREATE ON SCHEMA PUBLIC TO PUBLIC` on every new database, undoing PG15 hardening | Latent with one role; any additional login role gains CREATE in every tenant DB | `REVOKE` in provisioning | S |
| **SEC-3** | **RESOLVED 2026-08-23** — not by banning `**` but by removing `eval`: the substituted expression is parsed with `ast` and walked, and `ast.Pow` is simply absent from the allowed node types, so there is no pattern to get wrong. The root cause is worth keeping: a **character class cannot express "one star but not two"**, so `[0-9eE+\-*/(). ]*` was always going to admit `**`. Ten tests, including that the allowed arithmetic still evaluates, and one that asserts the *refusal* of `9**9**9` rather than evaluating it — a test that hangs the runner to prove a hang was fixed is a test nobody runs. A second bug fell out: sequential `str.replace` of box codes could rewrite digits inside a float it had already substituted, so substitution is now one pass with boundaries | Security | `vat_return.py:195,201` | Regex whitelist admits `**`; verified `9**9**9` passes `fullmatch` | Worker hang; with `workers=0` and `limit_time_real=0` the whole server. RCE **is** correctly blocked and tested | Done | XS |
| **SEC-6** | **RESOLVED 2026-08-23** — and it was **not** the one-character fix this row prescribed. That single row was also what granted every *higher* accounting group its access, because they all imply read-only; setting it to `1,0,0,0` alone would have stopped `action_compute` working, since computing a return unlinks and recreates every line. So the readonly row is now `1,0,0,0` and the billing and manager roles have rows of their own. Six tests, including that the read-only role can still *read* a line (which stops the fix becoming "delete the row") and that the billing role can still maintain them. A related hole surfaced while fixing it: `action_compute` checked no state, so a **filed** return could be recomputed in place and its filed figures would change with no trace — now refused until it is reset to draft | Security | `ir.model.access.csv:8` | `group_account_readonly` given write/create/unlink on VAT return lines | A read-only accountant can rewrite a filed return | Done | XS |
| **BS-3** | CONFIRMED | Bikram Sambat | `bs_accounting_dates.py:57-60`; `account_move_views.xml:365` | Search and group-by buckets stay Gregorian | A BS user filtering "August 2026" gets Bhadra 16 – Ashoj 15, straddling two BS months. **The most consequential functional gap** — BS presentation stops where periodic reporting begins | BS-aware period filter and group-by | L |
| **BS-4** | **RESOLVED** — settled 2026-08-23 by reading `nepali_calendar_core/tools/bs.py:160-172`: `month_length()` now bounds-checks the year and raises `UserError`, and its docstring records that it "previously did not, so an out-of-range year surfaced as a raw `KeyError`… reachable by default from BS 2097". Matches `docs/bs-calendar` BSC-4 "Done"; the BSD-7 "Not started" row in that same file is itself stale. See the module-move note under **BS-1** | Bikram Sambat | `bs.py:121-124`; `generate_np_fiscal_year.py:53,69` | `month_length()` raises raw `KeyError` at BS 2101 — the one entry point with no error wrapping — escaping the wizard's `UserError`-only catch | Traceback instead of a message; reachable by default from BS 2097 | Wrap + bound-check | XS |
| **BS-5** | LIKELY | Bikram Sambat | `bs_date_field.xml:14-20` | Input is uncontrolled (`t-att-value` → `setAttribute`), so the DOM diverges from the record after typing | Rejected entries stay on screen; picker updates don't refresh the box | Use `useInputField` | S |
| **BS-6** | CONFIRMED | Bikram Sambat | `bs_date_field.js:127-130` | "Today" from the raw browser clock, not `res.users.tz` | Widget and server disagree on today for part of each day | Derive from user tz | S |
| **BS-7** | CONFIRMED | Bikram Sambat | `bs_accounting_dates.py:70-81` | Name-based patching walks nested subviews of **other** models | Latent today; a future non-date field named `date` in a subview gets `bs_date` | Check `_fields[name].type` | XS |
| **BS-8** | CONFIRMED (rescoped 2026-08-15) | Bikram Sambat | `account_financial_report/report/open_items.xml:222,283,332`; `vat_report.xml:156,159`; `general_ledger.xml:116,118`; `aged_partner_balance.xml:100`; `layouts.xml:26` | **Superseded finding.** The old text blamed `bs_accounting_dates.py:57-60` ("only `form` and `list` patched; **all** PDF reports stay Gregorian"). That mechanism was retired — server-side BS now comes from the `ir.qweb.field.date`/`datetime` converter override (`nepali_calendar_core/models/ir_qweb_fields.py:34-76`), which is global and reaches core invoices, sale orders, delivery slips, payment receipts and the financial statements. It only reaches values emitted via `t-field`, or `t-out` with `t-options={'widget':'date'}`; a template calling `.strftime()` or printing a raw value bypasses it | Open Items and VAT Report print **no** BS at all; General Ledger and Aged Partner Balance print Gregorian period headers above BS line dates; every report footer timestamp is Gregorian. Already visible in the HTML variants — installing wkhtmltopdf did not cause it, but makes it reachable in PDF too | Route those through `t-field`, or call the existing `format_date_bs` QWeb global (`ir_qweb_fields.py:79-100`). No new conversion code needed | S |
| **ACC-4** | CONFIRMED | Accounting | `account.fiscal.position-np.csv:3` | Export FP `auto_apply=1` with no country | Also zero-rates foreign **vendors** — wrong under reverse charge | SME decision | S |
| **ACC-5** | CONFIRMED | Accounting | `l10n_np/data/template/account.account-np.csv:24` | `Tax Receivable` typed `asset_current` but sits in the 2xxxxx liability block | Reads wrong on a code-ordered trial balance | Re-code or re-type | XS |
| **ACC-6** | CONFIRMED | Accounting | `l10n_np_tds/data/ir_sequence_data.xml:6,9` | TDS sequence uses the **Gregorian** year and is **company-global** (`company_id=False`) | All tenants share one certificate series; the year rolls mid-Nepali-FY | Per-company sequence, BS year | S |
| **UPG-2** | **RESOLVED 2026-08-23** — the fix is the *check*, not the bump: `tools/check_module_versions.py` compares each module's last code change against the last commit that moved its `version` line, and fails on drift. Wired into `lint`. Bumping once would have been undone by the next change. It found **six** stale modules on first run (`account_financial_statements`, `account_reports_interactive`, `date_range`, `l10n_np_accounting`, `l10n_np_fiscal_year`, `l10n_np_tds`), all now bumped. Deliberately conservative: it flags pure-Python changes that did not strictly need a bump, because deciding "no data changed here" from a diff is exactly the judgement that goes wrong quietly | Upgrade | all 8 manifests | Zero migration scripts; every module frozen at `19.0.1.0.0` | Odoo never fires "outdated"; a deploy relying on version comparison skips them, leaving stale views and **ACLs** | Done | S |
| **UPG-3** | CONFIRMED | Upgrade | `res_config_settings_views.xml:10` | xpath `//block[@id='analytic']` `position="before"` — sibling-relative into the most-churned arch in Odoo | A rename → `ParseError` → **the module fails to install** | Target the ancestor with `position="inside"` | S |
| **UPG-4** | POSSIBLE | Upgrade | `wizard/account_lock_dates.py:18` | New model named `account.lock.dates` — inside core's namespace | If Odoo 20 adds that name, this silently *extends* it and the fields collide | Rename `l10n_np.account.lock.dates` | XS |
| **DAT-2** | **RESOLVED 2026-08-27** — deleted. Re-verified against the live database first rather than trusting the 2026-08-14 reconciliation: all five real blobs confirmed unreferenced by any `ir_attachment.store_fname`. The tree held **13 files / 11.96 MB**, not the 11 recorded here — it had also accrued **two stale session files**, which the original count missed. Scoped to `.odoo_data`; the stale `Downloads\odoo-19.0` tree itself is left for the user | Data | `…\Downloads\odoo-19.0\.odoo_data` | Orphaned filestore, 11 files, no repo/config/owner. Caused by OPS-1, which is now fixed so it receives no further writes | **Reconciled 2026-08-14: contains nothing of value** — 5 regenerable asset bundles + 6 blobs referenced by no database row. **Zero business attachments.** Originally rated as holding business documents; that was wrong | Safe to delete. The 5 dangling rows then return `b''` per `ir_attachment.py:151-155` | XS |
| **SCH-1** | **RESOLVED 2026-08-23** — `company_id` indexed on all ten company-scoped models, plus the one2many parents (`vat.return.box.form_id`, `vat.return.line.return_id`, `tds.certificate.line.certificate_id`), the named `vat.return.line.box_id`, and `partner_id` on the loan and the TDS certificate. Verified present in `pg_indexes`. Done immediately after SEC-2 for the reason this row predicted: those record rules put `company_id` in the WHERE clause of every query against these tables | Schema | custom tables | Business FKs unindexed | `company_id` became hot the moment SEC-2 added rules | Done | XS |
| **SCH-2** | CONFIRMED | Schema | all custom tables | **0 rows**; 3 posted journal entries cluster-wide | Nothing exercised at volume; no performance claim is evidence-based | Load representative data | M |
| **COD-1** | CONFIRMED | Tests | `test_loan.py` (10 sites) | Money compared with `assertEqual`; the `currency.round()` mitigation appears in exactly one test | Brittle across rate/term combinations | Round consistently | S |
| **COD-2** | **RESOLVED 2026-08-23** — moved to `tools/check_xml_wellformed.py`, run by `lint`, and the four duplicated `test_xml_is_well_formed` methods deleted. **Two corrections to this finding:** the `minidom` half is *stale* — no local code has used it for some time, and the one remaining mention is a comment in `test_menu_integrity.py` explaining that minidom is deliberately avoided *because* it accepts `--`. And the gap was larger than "missing from 3 of 8": **twelve** modules shipped XML with no such test, including `l10n_np_accounting` with six files. A fifth and sixth copy was not the fix. The check needs no ORM, so paying for a database and a module install to do a filesystem parse was the wrong trade, and a test could only ever cover modules that already had a `tests/` directory. The tool covers **79 files across 16 modules** — up from 14 — in about a second. Proved by introducing a `--` comment into `local_ui_tweaks`, a module that previously had no XML test at all |  Tests | 5 modules | `test_xml_is_well_formed` copy-pasted 5×, **missing from 3 of 8**; four copies use `minidom`, which accepts `--` in comments where Odoo's `lxml` rejects it | Four copies cannot catch the defect they exist for | One shared `lxml` mixin | S |
| **COD-3** | CONFIRMED | Packaging | 3 dirs | Empty package directories on disk but untracked | `git clone` ≠ working copy; the declared JS test bundle location does not exist on a fresh clone | Delete or `.gitkeep` | XS |
| **SEC-4** | CONFIRMED | Security | `abstract_wizard.py:67-75` | `sudo()` writes a global `ir.default` on every Export click; wizards open to `base.group_user` | Any employee writes a company-wide default | Local override | S |
| **SEC-5** | CONFIRMED | Security | OCA ACL CSVs | `base.group_user` CRUD on budget lines and the persistent age-report configuration | Non-accounting staff alter aged-balance bucketing | Tighten locally | S |
| **SEC-7** | CONFIRMED | Security | `l10n_ne/apply.py:88,112,148,179-181` | `--modules` unvalidated into `os.path.join`; no containment check | Operator-run, so bounded — an unguarded footgun in a routine tool | `os.path.commonpath` | XS |
| **SEC-8** | CONFIRMED | Security | `report_xlsx/controllers/main.py:27,36-41,100-104` | Bare `@route()` inherits auth invisibly; client context merged into rendering; `_serialize_exception` returned | Auth tracks upstream silently; info disclosure (escaped, not XSS) | Restate `auth=`; allowlist context | S |
| **CI-2** | **PARTIALLY ADDRESSED 2026-08-23, gate stays OPEN** — `deploy/Dockerfile` and `deploy/docker-compose.yml` now exist, pinning a patched-Qt wkhtmltopdf (the build fails if `--version` lacks "with patched qt", per DEP-6), asserting `nepali_datetime` imports, running as a non-root fixed uid, mounting the config rather than baking credentials, and using Odoo's own `/web/health`. **Neither has ever been built or run**: Docker is not installed on this machine. The compose file is YAML-parser-validated and that is all. Ticking this gate on an unbuilt Dockerfile would repeat FIN-2 and TST-5 exactly — code that "worked" until someone ran it | Environments | repo root | dev (Windows, `workers=0`) and prod (Linux, systemd) share no artefact; `run-odoo.sh` has never run | Nothing validates the Linux path | Build it once, then close | M |
| **DEP-2** | CONFIRMED | Dependencies | `requirements.txt:66-67` | `PyPDF2==2.12.1` installed and active (retired upstream) | PDF parsing is an attack surface for uploaded invoices | Move to `pypdf` | S |
| **DEP-6** | CONFIRMED (new 2026-08-15) | Dependencies | `.runtime/bin/wkhtmltopdf/`; `deploy/README.md` §1 | The PDF engine is unmaintained and unverifiable. The wkhtmltopdf packaging repo was **archived read-only 2023-08-28** — no releases, no security fixes. Its **last Windows build is 0.12.6-1 (2020-06-10)**, three years older than the 0.12.6.1-3 Odoo recommends and our docs used to mandate; 0.12.6.1-3 ships Linux packages only. Upstream publishes **no checksums or signatures** for it, by explicit statement in the release notes, so the binary cannot be verified against anything but TLS to github.com | A 2020 HTML/Qt renderer running server-side with no patch path. Bounded today — it renders only our own templates — but becomes a real exposure under database-per-tenant, where tenant-controlled content reaches it. Odoo 19 has **no** alternative engine: `_render_qweb_pdf` routes unconditionally to `_run_wkhtmltopdf` (`ir_actions_report.py:891`), and there is no weasyprint/chromium path in the tree | No clean fix. Either pin and vendor a known-good binary with a recorded hash (done: `.runtime/bin/wkhtmltopdf/PROVENANCE.txt`), or add a `_render_qweb_pdf` override via the `report_type` dispatch (`ir_actions_report.py:1148`) the way `report_xlsx` already does. Revisit before multi-tenancy | M |
| **TST-8** | **RESOLVED 2026-08-19** — the three test classes are now `@tagged("-at_install", "post_install")`, so they run with the full registry and `res.partner` carries `autopost_bills`. Full suite is **0 failed, 0 errors of 326**, green for the first time. The tests were never wrong: upstream CI installs only `web`, where the column does not exist, so the failure is specific to running them in a database that also has `account`. A local deviation from vendored upstream, recorded in `VENDORED.md` so an upgrade re-applies it. | Testing | `custom_addons/date_range/__manifest__.py` (`"depends": ["web"]`); `tests/test_date_range.py:18` | **15 of `date_range`'s 19 tests error**, every one with `null value in column "autopost_bills" of relation "res_partner" violates not-null constraint`. `date_range` depends only on `web`, so it loads — and self-tests — before `account`. Its `setUp` creates a `res.company`, which cascades into a `res.partner` INSERT. The column exists NOT NULL in the database (put there by `account`), but `account` is not in the registry yet, so the ORM omits it. Reproduced identically with `test-module date_range` alone and in the full suite, and with and without the `bin_path` change, so it is structural and pre-existing | The suite reports `0 failed, 15 error(s) of 304 tests` and `test` exits 1, so **no green run is currently achievable** — which defeats the whole point of a gate and hides the next real regression. Note TST-3 already warns that a green run is indistinguishable from a run of nothing; this is the inverse | Give `date_range` its tests a dependency-complete registry (add `account` to the test-run module set, or tag these tests `post_install`), or exclude the vendored module from the local gate and say so | S |
| **OPS-7** | **RESOLVED 2026-08-19** — `--db`/`--database` are now translated to `-Db` before use, so the header's own example works. `$Lines` had to become `[string]` and be validated in the body, because the failure happened during PowerShell's *parameter binding*, before any code of ours could run or explain. Any other POSIX flag is now a clear error naming the PowerShell spelling rather than being silently swallowed — `start --foreground` previously bound to the target argument and just did not start in the foreground. Verified across six invocation shapes. | Operations | `run-odoo.ps1:7,23-33` | **The script's own usage example cannot work.** Line 7 documents `.\run-odoo.ps1 upgrade l10n_np_accounting --db odoo19`, but `--db` is never parsed anywhere in the file — PowerShell binds it positionally, so `--db` lands in `$Db` and `odoo19` in `[int] $Lines`, failing with `Cannot convert value "odoo19" to type "System.Int32"`. `test --db odoo19` appears to work only by luck: with no target argument the tokens shift one place and `odoo19` happens to land in `$Db` | A user copying the documented POSIX form — or the `run-odoo.sh` syntax — gets a .NET cast error naming a parameter they never used. Not a safety hole: the destructive verbs refuse to run rather than targeting a wrong database. But the header advertises a form the script rejects | Either parse `--db`/`--database` explicitly, or correct the header and help to the PowerShell form `-Db`. Prefer the former, since both scripts are documented as one interface | XS |
| **SEC-12** | **RESOLVED 2026-08-21** (commit `614a368a`) — root gated on `account.group_account_readonly,account.group_account_invoice`, mirroring core; Dashboard on `group_account_basic` as core gates its own. Verified with `load_menus()`: a user with no accounting group went from a visible tile with 8 reachable entries to no tile and 0. `test_menu_visibility.py` gained the case it never had, and its `ALWAYS_VISIBLE` constant — which had encoded this defect as intended behaviour — is now `UNGATED_SECTIONS`. | Security | `l10n_np_accounting/views/np_accounting_menus.xml:22-25`; compare `odoo/addons/account/views/account_menuitem.xml:5-8` | **The "Accounting Nepal" root menu has no `groups=` at all.** Core's equivalent `account.menu_finance` gates on `account.group_account_readonly,account.group_account_invoice`. Verified with `_visible_menu_ids()` — the API the web client uses, not `search()`, which ignores groups: a user holding **none** of the accounting groups (`salesexecutive@example.com`) sees the tile and **8 reachable entries** — Customers, Vendors, Products (×2) and **Employee Expenses** (`hr.expense`) | Not merely a stray tile. An accounting application presents itself to every internal user, and the reachable actions target `res.partner`, `product.template` and `hr.expense`. Model-level ACLs still apply, so this is exposure of *navigation*, not a direct read of accounting data — but a sales user reaching Employee Expenses under an accounting banner is wrong on its face, and the same omission on any future child menu would expose that child too. Found while tracing a report of "installed app has no entry point" | Gate the root on `account.group_account_readonly,account.group_account_invoice` to match core, and audit the intermediate menus (`Customers`, `Vendors`) which are ungated for the same reason. Test with `_visible_menu_ids()` for a user holding no accounting group | S |
| **FIN-3** | **RESOLVED 2026-08-19** (found and fixed same day) | Accounting | `account_financial_report/wizard/aged_partner_balance_wizard.py:137`; `report/aged_partner_balance.py:419` | **Aged Partner Balance could not render at all.** The wizard passed `date_at` as a `datetime.date` while the report immediately called `strptime(date_at, "%Y-%m-%d")`, so pressing Export HTML, PDF or XLSX raised `TypeError: strptime() argument 1 must be str, not datetime.date`. Verified by calling `button_export_html()` and rendering the returned action, which is what the web client does. The sibling report gets it right (`open_items_wizard.py:172` uses `fields.Date.to_string`) and `general_ledger.py:793` guards with `isinstance(..., str)`, so the convention exists in the same module and this one call site missed it | One of the six OCA reports was completely unusable, and had been for as long as it has been vendored. **Its own tests pass** — they call `_get_report_values` directly with a hand-built string and so never cross the boundary where the types disagree. That is the third instance in this project of the FIN-2 pattern: green tests over a report that has never rendered. It also explains why the eight broken drill-down attributes went unnoticed for so long — nobody could reach the page to click them | Fixed by model override in `account_reports_interactive/models/aged_partner_balance_wizard.py`, not in place (AGPL-3, `VENDORED.md`). An upstream fix supersedes it harmlessly, since converting an already-correct string is a no-op. Worth reporting upstream | XS |
| **COD-11** | CONFIRMED (new 2026-08-17) | Code quality | `account_financial_report/report/trial_balance.py:242,542`; `general_ledger.py:948-972`; `report/templates/general_ledger.xml:224-251`, `trial_balance.xml:325-367` | OCA's reports **discard the drill-down domain they already computed** and rebuild it by hand in QWeb. `trial_balance.py` uses `_read_group`'s `__domain` internally and never exports it; `general_ledger`'s report values contain no `domain` key at all. So every clickable figure's domain is reassembled from ids in the template, in 14 places in general_ledger and 28 in trial_balance | One root cause behind three separate symptoms: the aged-balance drill-down was written with 8 broken `domain=` attributes and never worked at all (repaired 2026-08-17 by overlay in `account_reports_interactive`); `open_items` and `journal_ledger` have no amount drill-down; and nothing structurally guarantees a rebuilt domain still matches the figure above it. Our own statements avoid this by returning the domain from the same call that computed the number, which is what makes their invariant testable | Persist the domain onto each line dict, as `account_financial_statements` now does. **Python change to AGPL-3 vendored code**, so it needs an overlay module or an upstream PR rather than an in-place edit | M |
| **DOC-3** | **RESOLVED 2026-08-23** — `date_range` added to the table; "two of the three are AGPL-3" corrected to **five of seven**, derived from the seven `license` keys. Note the finding itself said "four of seven" and was also wrong — **LIC-1 rests on this count**, so it is now derived rather than quoted | Documentation | `custom_addons/VENDORED.md` | Omits `date_range`; "two of the three are AGPL-3" when it is **four of seven**; lists 2 of 8 local modules; misstates the §13 trigger as modification | Understates AGPL exposure by half; feeds LIC-1 | Rewrite against manifests | S |
| **DOC-4** | CONFIRMED | Documentation | 5 root docs | All describe a repo with one local module; `RUNTIME-ARCHITECTURE.md` never mentions `custom_addons` | Stale by 8×; omits the `_get_view` patcher | Date-stamp as snapshots | S |
| **OPS-3** | CONFIRMED | Operations | `deploy/odoo.service:18,51`; `README.md:45` | Service account owns `/opt/odoo` incl. its venv; `ProtectSystem=full` leaves `/opt` writable; missing `PrivateDevices`, `RestrictAddressFamilies`, `SystemCallFilter`, `MemoryMax`, `UMask`; `-s /bin/bash` | Code-execution bugs become persistent. Note the tension: `-u` and SUP-3 both want `/opt/odoo` writable | `ProtectSystem=strict` + `ReadWritePaths`; `nologin` | S |
| **OPS-4** | CONFIRMED | Operations | `odoo.conf:60`; `.example:68` | `limit_time_real = 0` disables the runaway-request watchdog | One tenant's infinite loop permanently consumes a thread — a cross-tenant availability path. The Windows rationale is sound for dev; it must not ship | Restore on Linux (already correct there) | XS |
| **TST-9** | **RESOLVED 2026-08-23** — `tools/check_test_wiring.py` parses every `tests/__init__.py` with `ast` and fails when a `test_*.py` file is not imported, or when an import names a file that no longer exists. Wired into `lint`, so it runs in seconds without a database or a suite run. Proved against both failure modes by reproducing the original ACC-3 mistake exactly. It also found a UTF-8 BOM (**QA-2**) on its first run, which is why it reads with `utf-8-sig` | **RESOLVED 2026-08-23, same day it was introduced** | Testing | `custom_addons/l10n_np/tests/__init__.py` | Adding a test file for ACC-3, I overwrote this `__init__.py` with only the new import and unwired the five pre-existing `test_np_chart` tests. The suite still reported `0 failed, 0 error(s)`, exit 0, **zero skips** — only the total moved, 343 to 342 | An unimported test file is indistinguishable from one that never existed. TST-3 warns about tests that skip themselves, but a skip is at least *reported*; this is the silent version, and it survives a green gate | Compare `def test_` methods on disk against the count the runner reports — 347 vs 342 here, and the difference is exactly the unwired file. Cheap enough for CI (**CI-1**) | XS |
| **TST-3** | **RESOLVED 2026-08-23** — in two halves. The *reporting* half landed with CI-1: `test` now prints the skip count, names every skipped test, and `--fail-on-skip` exits non-zero for CI, because Odoo tracks `result.skipped` internally and never prints it. The *skipping* half is this sweep: **11 conditional skips became 3**. Every skip that fired because a fixture was merely **absent** — no chart, no journal, no open items, no journal activity — now creates that fixture instead, searching first so an existing chart is still used. Two of the account types involved (`asset_fixed`, `liability_non_current`) are ones `ACCOUNTING_NEPAL.md` records as *missing from this 43-account chart*, so the cash-flow suite was one chart revision from asserting nothing. The 3 that remain are deliberate and annotated as such: two guard assertions that are *meaningless* off the Nepali chart rather than inconvenient, and one needs `node` on PATH. All three are now reported rather than silent | Testing | `test_reconcile.py:48-50`; `test_bs_accounting_dates.py:42-46` | Whole suites gate on one skip; nothing reports skip counts | A green run is indistinguishable from a run of nothing | Fail CI on skips | S |
| **TST-6** | CONFIRMED | Testing | `test_loan.py:243-259` | Hardcoded 2026 backdates mixed with `context_today` | Holds only while the clock is past Feb 2026 | `freezegun` | XS |
| **TST-7** | **PARTLY RESOLVED 2026-08-23** — the company half is measured and is **not** a problem: `res_company` held 1 row before a test run that creates several throwaway companies, and 1 row after. Creating a company and writing to it roll back together; the `cr.precommit` hazard applies to writes against a company that **already existed** (which is what `test_lock_dates.py` warns about and why it, and the new TST-5 fixture, build their own). The `base.group_user.implied_ids` half is untested and still open | Testing | `test_lock_dates.py:22,79`; `test_bs_accounting_dates.py:30` | ~7 throwaway `res.company` per run; `base.group_user.implied_ids` mutated globally | Companies do not accrete. A global group mutation still would | Re-measure `implied_ids` the same way | XS |
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
