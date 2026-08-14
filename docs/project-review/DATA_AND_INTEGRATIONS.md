# Data and Integrations

Findings referenced by ID; full evidence in [`BACKLOG.md`](BACKLOG.md).

## 1. The data-integrity defect — OPS-1 (**RESOLVED 2026-08-14**)

> Fixed. `addons_path` and `data_dir` corrected; reconciliation proved **no data loss** (0 business
> attachments missing, the only `Downloads`-exclusive content being regenerable asset bundles); both
> launchers now refuse to start on a missing path. Verified by downloading real attachments with
> byte-exact sizes. Full evidence in `BACKLOG.md` under OPS-1. Original description retained below.


The running `odoo.conf` points at directories that no longer exist:

```
addons_path = C:\Users\i81129\Downloads\odoo-19.0\odoo\addons      → does not exist
              C:\Users\i81129\Downloads\odoo-19.0\custom_addons    → does not exist
data_dir    = C:\Users\i81129\Downloads\odoo-19.0\.odoo_data       → exists, but is the wrong one
```

The project was moved to the OneDrive/Desktop path and the config was not updated. Two
consequences, of different severity:

- **Modules cannot load.** Building the registry emits `Some modules are not loaded…` listing all
  15 custom modules. Recoverable by editing one line.
- **The attachment layer is splitting.** `data_dir` resolves to an orphaned filestore holding
  **11 blobs**, while the database references **572** in the OneDrive filestore. Twelve files
  were written to the orphan on 2026-08-14. Existing attachments are unreadable; new ones land
  where nothing else looks.

This was silent and ongoing. **Update (2026-08-14): reconciled and fixed.** Matching
`ir_attachment.store_fname` against both trees showed **0** referenced blobs missing from both and
**0** business attachments absent from the live filestore — the orphan held only regenerable asset
bundles. The warning that it "may hold the only copy of recently written attachments" was
disproven by measurement.

## 2. Schema

### Custom tables

| Table | Rows | Indexes |
|---|---:|---|
| `l10n_np_loan` | 0 | pkey only |
| `l10n_np_loan_line` | 0 | pkey, `loan_id`, `date` |
| `l10n_np_tds_category` | 0 | pkey only |
| `l10n_np_tds_certificate` | 0 | pkey only |
| `l10n_np_vat_return` | 0 | pkey only |
| `l10n_np_vat_return_line` | 0 | pkey only |
| `l10n_np_vat_return_form` | 0 | pkey only |
| `l10n_np_vat_return_box` | 0 | pkey only |

**Every custom table is empty** (SCH-2), and the database contains only 3 posted journal entries
in total. Nothing has been exercised at any realistic volume, so no performance claim about this
suite is evidence-based. That is expected for a suite that deliberately ships with empty rate and
form tables — but it also means the first real month of data is the first real test.

**SCH-1** — business foreign keys are unindexed: `vat_return_line.return_id`, `.box_id`,
`loan.partner_id`, and `company_id` throughout. `loan_line.loan_id` and `.date` *are* indexed, so
the pattern was understood and applied inconsistently. Low impact at present volumes;
`company_id` becomes hot once SEC-2 adds record rules, since every query then filters on it.

### Transactions and concurrency — verified safe

Odoo runs **REPEATABLE READ** (`odoo/sql_db.py:373`) and retries serialization failures up to
five times (`odoo/service/model.py:29-30`). The money-posting paths in `l10n_np_loan` guard
idempotency with an in-memory `line.state == 'posted'` check; a concurrent double-post loses on
the row UPDATE, is retried, re-reads `posted`, and raises. **No row locking is required and none
is a defect.** Checked rather than assumed.

One genuine transactional subtlety the code already handles: writes to `res.company` are flushed
through `cr.precommit` and can outlive `cr.rollback()`. The lock-dates and BS-date test suites
create throwaway companies specifically to avoid corrupting the real one, with comments
explaining why. See TST-7 for the residual question.

## 3. Source-of-truth and staleness

| Data | Source of truth | Risk |
|---|---|---|
| Accounting ledger | PostgreSQL `odoo19` | — |
| Attachments | filestore on disk | ~~split across two trees~~ — single tree since the OPS-1 fix |
| Code translations | `.po` on disk inside vendored core | wiped by any Odoo upgrade (SUP-3) |
| Model translations | jsonb columns | survives upgrades — hence the *asymmetry* that makes SUP-3 hard to spot |
| Nepali translation corpus | `l10n_ne/po/*.po` (committed) | two copies exist — `l10n_ne/po/` and `odoo/addons/*/i18n_extra/` — reconciled only by manually re-running `apply.py`; nothing detects divergence |
| Bikram Sambat calendar | `nepali_datetime` (Python) **and** a generated JS table | two implementations, no cross-check in any test (TST-4) |
| View architecture | `ir.ui.view` + a runtime `_get_view` patcher | cache key correctly extended with group and company digit style |

The two duplicated-source rows are the ones to watch. Both are documented, neither is monitored.

## 4. Data protection — DAT-1

Inside the corporate OneDrive sync root:

| Item | Size | Sensitivity |
|---|---|---|
| `.odoo_data/odoo19_before_oca.dump` | 9.3 MB | **full database image** — user password hashes, partner PII, whole ledger |
| `.odoo_data/odoo19_before_phase1.dump` | 9.5 MB | as above |
| `.odoo_data/filestore/` | 113 MB / 572 blobs | **98% regenerable asset bundles**; the business content is 1.8 MB across 921 rows |
| `.odoo_data/sessions/` | 299 KB / 75 files | **live server-side session material** |
| `odoo.conf` | 2.9 KB | master + database passwords |
| `.git` | 337 MB | full history |
| `venv/` | 168 MB | platform binaries |

`.gitignore` correctly excludes most of this from **git** and has no bearing whatsoever on
**file sync**. There is no sync-side exclusion configured.

Two distinct risks:

- **Confidentiality** — complete database images and session material replicated to a cloud
  tenant, subject to its sharing links, retention and eDiscovery.
- **Integrity** — git assumes exclusive local-filesystem semantics. A `gc`/`repack` rewriting
  328 MB of packs while the sync client holds handles is the classic corruption case. With no
  remote (SUP-2), the corrupted copy would be the only copy, and sync would propagate rather
  than protect.

The `.odoo_data` filestore is also *not* a backup even though it is being synced: it is only
meaningful paired with a database dump taken at the same instant. A continuously drifting copy
creates false confidence in a restore path that does not work.

**DAT-2** — a second, orphaned filestore sits at the old `Downloads` path with no repo, config or
owner. It stopped receiving writes when OPS-1 was fixed, and reconciliation showed it holds nothing
of value: 5 regenerable asset bundles plus 6 blobs referenced by no database row. Safe to delete.

## 5. External dependencies

| Dependency | Declared where | In `requirements.txt`? | Pinned? |
|---|---|---|---|
| `nepali_datetime` | `l10n_np_bs/__manifest__.py:36` | **No** (DEP-1) | No |
| `python-dateutil` | `account_asset_management` | Yes | Yes |
| `xlsxwriter`, `xlrd` | `report_xlsx` | Yes | Yes |
| `polib` | used by `l10n_ne/apply.py` | **No** | No |
| `websocket-client` | needed by the one JS test | **No** | — |

**DEP-1 is the blocker**: `external_dependencies` is not read by pip, so an environment built
from `requirements.txt` fails Odoo's dependency check on `l10n_np_bs`, and because the umbrella
depends on it, **the entire suite is uninstallable on a fresh machine**. The package exists in
the current venv only because it was installed by hand.

**COD-10** — `l10n_np_bs/tools/bs.py:124` calls the private `nepali_datetime._days_in_month`. The
import itself is guarded and degrades with a clear error; the private symbol is the fragile part,
and with no version pin any upgrade can remove it. The failure mode is wrong Bikram Sambat dates,
which propagate into fiscal-year boundaries and VAT return periods.

**DEP-2** — `PyPDF2==2.12.1` is installed and active (this venv is Python 3.12; line 68 correctly
uses `pypdf` only for ≥3.13). PyPDF2 is retired upstream and receives no security fixes; PDF
parsing is an attack surface for uploaded invoices. Needs an advisory check this audit could not
perform.

**DEP-3/DEP-5** — `requirements.txt` is stock upstream with no project-owned additions, and the
vendored OCA provenance is recorded as branch URLs plus a date rather than commit SHAs, with an
update procedure using `--depth 1` on a moving branch. Zero drift today, but non-reproducible.

## 6. Integrations

There are **no outbound integrations** — no external APIs, webhooks, message queues or scheduled
syncs in any locally written module. Consequently there is nothing to assess for pagination,
retries, timeouts, rate limits or idempotency at an integration boundary. The only network
surface is Odoo's own HTTP layer plus the two vendored report controllers (SEC-8).

This is worth stating explicitly: several standard audit categories are empty by design, not by
oversight.

## Recommended sequence

1. ~~**OPS-1**~~ — **done 2026-08-14**; paths corrected, reconciled, launcher guard added.
2. **DAT-1** — move out of sync, or exclude `.git`/`.odoo_data`/`venv`; relocate the dumps.
3. **DEP-1** — declare and pin `nepali-datetime` (and `polib`, `websocket-client`).
4. **DAT-2** — reconciled (nothing of value); removal awaiting approval.
5. **SCH-1** — add indexes, ideally alongside SEC-2's record rules.
6. **SCH-2** — load a representative dataset and re-measure before go-live.
