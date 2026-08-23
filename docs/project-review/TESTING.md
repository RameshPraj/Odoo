# Testing

Findings by ID in [`BACKLOG.md`](BACKLOG.md).

## Summary

**326 test methods across 17 modules, and they pass.** The volume is respectable. The placement is
not: **every one of the four correctness defects in this audit is covered by a green test that
exercises the wrong layer.** That remains the point of this document — a green suite is now available
as a baseline, which makes the placement problem the *only* remaining one, not a second one.

> **Updated 2026-08-19.** The original sentence — "121 test methods across 8 modules, and nothing runs
> them" — was wrong in both halves. `run-odoo.ps1 test` / `run-odoo.sh test` runs them (**CI-1** is
> partially resolved: a runner exists, automation still does not), the count is 326, and as of
> 2026-08-19 the result is **0 failed, 0 errors**. The intermediate state recorded here on 2026-08-15
> — 15 `date_range` errors — was **TST-8**, now fixed.

| Defect | The test that should have caught it | Why it did not |
|---|---|---|
| FIN-2 — reports cannot render *(fixed 2026-08-15)* | 13 statement tests | All call `_get_report_values()` directly, bypassing the report engine. The dispatch test asserts on the `report_name` **string** and never renders |
| FIN-3 — OCA's Aged Partner Balance cannot render *(fixed 2026-08-19)* | 2 aged-balance tests | Worse than bypassing: they **compensate**. `test_aged_partner_balance.py:63,98` convert `date_at` to a string themselves, which is exactly the conversion the wizard fails to do — so the tests encode the workaround and can never see the defect |
| FIN-1 — VAT boxes are nil | `test_box_from_tax_tags_ties_to_ledger` | **Skips when there are no tags** — i.e. under exactly the condition that indicates the bug |
| ACC-1 — loans post wrong currency | `test_drawdown_entry_is_balanced…` | Asserts the entry **balances**. It does, in the wrong currency |
| TST-5 — TDS reports zero withheld | 10 TDS tests | None calls `action_collect_lines`, the only method that touches the ledger |
| ACC-3 — exports taxed at 13% *(fixed 2026-08-23)* | none existed | `l10n_np`'s five tests assert the chart *loads* — accounts wired, VAT rate 13%, provinces present. Nothing created an invoice, so the position could be applied and substitute nothing with every test green. The new tests assert the invoice, in both directions |

That is the single most important observation in this document. The suite tests mechanism
thoroughly and outcomes barely at all.

## Inventory

| Module | Tests | Notes |
|---|---|---|
| `l10n_np` | 5 → **9** | chart, taxes, provinces; + 4 on export zero-rating (ACC-3, 2026-08-23) |
| `l10n_np_bs` | 7 | + **669 lines of untested JS** (TST-4) |
| `l10n_np_fiscal_year` | 7 | the only suite with proper fixtures |
| `l10n_np_tds` | 10 | the figure-producing path untested (TST-5) |
| `l10n_np_vat_return` | 10 | the ledger-tie test skips (TST-1) |
| `l10n_np_loan` | 22 | best coverage; see ACC-1 for the gap it leaves |
| `account_financial_statements` | 13 | logic covered, **rendering never exercised** (FIN-2) |
| `l10n_np_accounting` | 47 | menus, visibility, lock dates, reconcile, BS dates |
| **Total** | **121** | plus 95 inherited with the vendored OCA modules |

Every module has tests and every `tests/__init__.py` wires them correctly — no silently unwired
suites.

> **This claim was briefly false, by my hand, on 2026-08-23**, and is worth leaving as a warning
> rather than a clean assertion. Adding a test file to `l10n_np` I overwrote its `tests/__init__.py`
> and unwired the five that were already there. Restored the same day; see **TST-9**. The lesson is
> that "wired correctly" is a property nothing in this repo checks, so it holds only until the next
> person adds a file — a green run says nothing about it.

## Structural defects

**TST-1 — a test that disables itself when the thing it guards is broken.** Verified firing on
the live database today. Replace the skip with an assertion and build the tax, tags and invoice as
fixtures.

**TST-2 — five suites assert on live database state.** Three assert the database is *empty*
(`test_ships_with_no_form`, `test_ships_with_no_rates`, `test_is_configured_flag`) and will fail
permanently the day an accountant configures TDS rates or an IRD form — the day the modules do
their job. The correct pattern already exists at `test_np_fiscal_year.py:20-26`, added after this
exact bug bit, and was never propagated to the other seven.

**TST-3 — whole suites gate on a single skip, unreported.** Six of seven reconcile tests, and all
14 BS-date tests (the skip sits in `setUp`). Evaluated live, neither currently fires — but that is
incidental, nothing reports it, and TST-1 proves the mechanism bites.

**TST-4 — 669 lines of JavaScript with zero tests.** `static/tests/` is declared in the manifest,
is empty, and is untracked — so it does not exist on a fresh clone. The only JS assertion checks
that a grid of >20 cells rendered; it never validates a date.

**TST-9 — a new test file can silently switch off the old ones, and the suite still reports
green.** Recorded because it happened here, to me, on 2026-08-23. Adding
`l10n_np/tests/test_fiscal_positions.py` for ACC-3, I overwrote `tests/__init__.py` with a single
`from . import test_fiscal_positions` — dropping the existing `from . import test_np_chart` and
disabling five pre-existing tests. The plan for that work asserted "the module has no `tests/`
directory yet"; it did, containing a file committed on 2026-08-09. Nothing complained: the run was
`0 failed, 0 error(s)`, exit 0, **zero skips**. Only the total moved, 343 to 342, and 342 is not a
number that looks wrong.

What caught it was refusing to round the total. What *confirmed* it was counting `def test_`
methods on disk (347) against the count the runner reported (342) — the two reconcile exactly once
the five unimported tests are accounted for, and 343 − 5 + 4 = 342 closes from the other side too.
That disk-versus-runner count is a five-second check and the only one here that would have detected
this class of loss.

This is TST-3's warning arriving from an unexpected direction: TST-3 is about tests that skip
themselves, where at least a skip is *reported*. An unimported test file reports nothing at all —
it is indistinguishable from a test that never existed. A `-a` on the wrong redirect operator would
be more visible.

**BS-1 — the exhaustive cross-check is dead code.** `tools/selftest.py` already performs the
46,022-day Python↔JS sweep and nothing invokes it.

## Quality issues

- **COD-1** — money compared with `assertEqual` at 10 sites in `test_loan.py`; the correct
  `currency.round()` mitigation appears in exactly one test and `assertAlmostEqual` in two others
- **COD-7** — `assertRaises(Exception)` catches anything, including a typo in the test
- **TST-6** — hardcoded 2026 backdates; the assertion holds only while the clock is past Feb 2026
- **COD-2** — `test_xml_is_well_formed` copy-pasted 5×, missing from 3 of 8 modules, and four
  copies use `minidom`, which accepts `--` inside comments where Odoo's `lxml` rejects it
- **TST-7** — ~7 throwaway companies created per run; needs verification that they do not accrete

## What is done well

- `l10n_np_loan` genuinely proves the amortisation engine: every method closes to exactly zero,
  zero-rate loans do not divide by zero, and an unpayable rate is refused with a sentence
- `l10n_np_accounting` asserts menu visibility through `load_menus` — the only path that applies
  group filtering — a deliberate choice recorded after a `search()`-based check gave a false result
- The RCE test on the VAT formula evaluator is real and passes
- Test docstrings are unusually good, several citing the incident that motivated them

---

# Cross-tenant isolation tests — the specification

None of these exist. They are the deliverable that proves tenant A can never reach tenant B, and
they should be written **before** the SaaS pivot, not after. Each maps to a finding.

The suite needs two databases — call them `t_alpha` and `t_beta` — provisioned the way production
will provision them. Anything less tests a fiction.

### 1. Session cookie issued for A is rejected by B — SAAS-5, SAAS-1
```
GIVEN a valid authenticated session cookie for t_alpha
WHEN  it is presented on a request that resolves to t_beta
THEN  the response is unauthenticated (login redirect), and
      the server-side session's db is not silently rebound to t_beta
AND   a session token minted in t_alpha fails check_session in t_beta
      even for the same uid  (proves database.secret differs)
```
The last line is the important one — it is the primitive everything else leans on. Assert
directly that `t_alpha`'s and `t_beta`'s `database.secret` values differ, because a
template-clone provisioning bug would silently make them equal.

### 2. `dbfilter` rejects a non-matching database, by every route — SAAS-1, SAAS-4, SAAS-11
```
FOR each selector: Host header, X-Odoo-Database header, ?db= query param,
                   and the db argument of /web/session/authenticate
  WHEN a client requests t_beta while the Host maps to t_alpha
  THEN the request does not reach t_beta's registry
AND  an unanchored filter is rejected by the test itself:
     a database named t_alpha_staging must NOT be reachable from t_alpha's host
```
That final assertion is what catches the `.match()`-vs-`.fullmatch()` trap.

### 3. Filestore containment — SAAS-12
```
GIVEN an ir.attachment stored in t_alpha
THEN  its file lives under data_dir/filestore/t_alpha
AND   no path constructed from t_beta resolves into t_alpha's directory
AND   an attachment id from t_alpha, requested while bound to t_beta, 404s
```
Include a traversal attempt in the attachment path (`../`, `..:`) to assert `_full_path`'s
stripping still holds.

### 4. Database-manager routes are unreachable — SAAS-2, SAAS-6, SAAS-10
```
WITH list_db = False and a strong admin_passwd
THEN /web/database/manager, /selector and /list are blocked at the edge
AND  POST /web/database/create with any master_pwd does NOT change admin_passwd
     (the insecure-default auto-set branch must be dead)
AND  /web/database/backup refuses without the correct master password
```
The second assertion is the regression test for the live cluster takeover. Assert
`verify_admin_password('admin')` is **False**.

### 5. PostgreSQL-level isolation — PG-1, PG-2, PG-4
```
GIVEN a second login role (e.g. a reporting user)
THEN  it cannot CONNECT to any tenant database
AND   it cannot CREATE in any tenant's public schema
AND   the odoo role cannot SELECT from any table in an unrelated database
AND   dblink and postgres_fdw are absent from every tenant database
```
Run this as a provisioning acceptance test, so a newly created tenant is proven closed rather than
assumed closed.

### 6. Cron fan-out is scoped — SAAS-7
```
GIVEN t_beta is suspended (excluded from the routing allowlist)
WHEN  the cron sweep runs
THEN  no job executes against t_beta, and no mail is queued or sent from it
```
This is the test that catches the `db_name` removal described in
[`SAAS_MULTI_TENANCY.md`](SAAS_MULTI_TENANCY.md) as the riskiest edit in the pivot.

### 7. Backup and restore do not bleed — lifecycle
```
GIVEN a backup of t_alpha
WHEN  it is restored as t_gamma
THEN  t_gamma has a NEW database.secret (sessions from t_alpha do not authenticate)
AND   t_gamma's filestore contains only t_alpha's attachments, in t_gamma's directory
AND   t_alpha is unchanged
```

### 8. Offboarding leaves nothing behind — lifecycle
```
WHEN t_beta is deleted
THEN its database is dropped
AND  its filestore directory is gone
AND  no session file in the shared store belongs to t_beta
AND  its ir.mail_server credentials are revoked
```
The third assertion matters because the session store is shared (SAAS-5); offboarding is the point
where residue is most likely.

### 9. Noisy neighbour is bounded — OPS-4, SAAS-8
```
GIVEN a request in t_alpha that runs past limit_time_real
THEN  it is terminated and t_beta continues to serve within its normal latency budget
AND   exhausting connections from t_alpha does not deny service to t_beta
```
The second half will fail today (SAAS-8: one global pool) — which is precisely the point of
writing it.

---

## Recommended sequence

1. **BUG-6 / DEP-1** — make the suite installable at all. **XS**
2. **STORY-1 / CI-1** — one command runs everything and **reports skip counts**. **M**
3. **TST-1** then **FIN-1** — fix the test that hides the defect *before* the defect, so you can
   watch it fail and then pass. **S + M**
4. **FIN-2** — add a render assertion; it would have caught the P0 with one line. **S**
5. **BS-1** — wire in `selftest.py`. **S**
6. **TST-5**, **ACC-1**, **ACC-2** — tests for the untested money paths. **S each**
7. **TST-2** — fixtures everywhere; assert module data, not database emptiness. **M**
8. **COD-2** — one shared `lxml` mixin across all eight modules. **S**
9. **Cross-tenant isolation suite** above — before the SaaS pivot, not after. **L**
