# Technical Debt

Findings by ID in [`BACKLOG.md`](BACKLOG.md). Debt here means *structural cost being paid
repeatedly*, distinct from defects. Ordered by what it costs to keep paying.

---

## 1. The vendored core — SUP-1, SUP-4

51,775 of 52,523 tracked files (98.6%) are upstream Odoo, committed as a **source distribution**:
`PKG-INFO:3` reads `19.0.post20260807` and `odoo.egg-info/` is present. No upstream remote, no
common ancestor with `odoo/odoo`.

**Interest paid daily**
- Security releases cannot be merged — there is no shared history to three-way merge against.
- The only upgrade path is extracting a tarball over `odoo/` and committing a bulk diff, in which
  a security fix is indistinguishable from unrelated churn.
- No machine-checkable record of which build this is, so you cannot determine whether the core is
  patched.
- ~328 MB clone / 1.8 GB checkout for ~17 MB of project work — 30:1.
- `git log --name-only` over any upstream-touching range is unusable for review.
- Multiplies the DAT-1 cloud-sync surface roughly twentyfold.

**Options** (SPIKE-1 — do not take casually)

| Option | Effect | Cost |
|---|---|---|
| Install Odoo as a pinned dependency; keep only `custom_addons/` in the repo | Conventional Odoo-project layout. Solves SUP-1, SUP-4, most of DAT-1, and dissolves SUP-3's habitat | XL, forces a decision on SUP-3 |
| Submodule pinned to an `odoo/odoo` tag | Restores upstream identity and merge ability, keeps one checkout | L–XL |
| Re-base onto a real clone at the matching tag | Preserves layout, restores merge ability | XL, history rewrite |
| Status quo | Debt compounds with every Odoo CVE | — |

---

## 2. Patches inside the vendored tree — SUP-3

87 generated `ne.po` files live in `odoo/addons/<mod>/i18n_extra/` because Odoo resolves code
translations by module path — there genuinely is no addons-path-external location. The mechanism
is defensible; its **unmanaged** state is the debt.

The upgrade path and the patch mechanism are in **direct conflict**, and the conflict is
documented only in a docstring (`l10n_ne/apply.py:31-33`). Nothing enforces the "rerun this
script" step, and the failure is asymmetric — code strings revert while database-stored model
translations survive, so the UI ends up half-translated rather than cleanly reverted.

There are also **two copies of the same data** — `l10n_ne/po/*.po` and the deployed files —
reconciled only by manually re-running `apply.py`, with nothing detecting divergence.

**Reduce now:** scripted upgrade runbook plus a health check counting deployed files.
**Dissolve later:** largely disappears under option 1 of SUP-1.

---

## 3. No verification harness — CI-1, QA-1

304 tests across 16 modules, run only by hand — `run-odoo.* test` exists, but no automation invokes
it, and the suite currently exits non-zero on 15 pre-existing `date_range` errors (**TST-8**), so
there is no green baseline to protect. No linter configured despite `# noqa` annotations throughout —
including `S307` on a live `eval()`, which reads as a dismissed security warning with nothing
re-checking it.

The cost is already measurable: four consecutive commits (`b2570489`, `d9b0bc4a`, `fcb814f3`,
`cb96ff96`) are same-day fixes for defects a test run would have caught.

**This is the cheapest large win available**, and everything else gets safer once changes are
verified.

---

## 4. Tests that exercise the wrong layer — FIN-2, FIN-1, ACC-1, TST-1, TST-2, TST-5

The deepest debt in the codebase, because it is invisible: **all four correctness defects in this
audit are covered by green tests.** Statement tests call `_get_report_values()` and never render;
the loan test asserts the entry *balances*, which it does in the wrong currency; the VAT test
*skips* under exactly the condition that indicates the bug.

Related: five suites assert against live database state, and three assert the database is *empty*,
so they fail permanently once the modules are used as intended. The correct fixture pattern exists
in one module — added after this exact bug bit — and was never propagated to the other seven. That
is the signature of debt: the fix is known, understood, and unapplied in seven places.

---

## 5. Duplication with no shared home — COD-2, COD-8, COD-9, BS-1, TST-4

No shared test-helper module exists, so common checks are copy-pasted:

- `test_xml_is_well_formed` × 5, **missing from 3 of 8** modules, and four copies use `minidom`,
  which accepts `--` inside comments where Odoo's `lxml` rejects it — so those four cannot catch
  the defect they exist for
- Menu-tree walker × 3 in a single file
- Date-order validation × 4 with four different messages
- Two independent AD↔BS implementations, cross-checked by a `selftest.py` that nothing invokes

A single `custom_addons/l10n_np_testing/` helper module would retire most of this.

---

## 6. Versioning and migration — UPG-2

All eight modules frozen at `19.0.1.0.0` across ~15 feature commits including schema-changing
ones, and **zero `migrations/` directories**.

Odoo triggers upgrades on version increase, so this removes the upgrade path entirely: deploying
new code depends on someone remembering `-u`. Forget it and the database keeps old views, menus
and **access rights** while the source has moved on.

It also means FIN-1's fix has nowhere natural to live — a data migration needs a version bump to
run at all.

---

## 7. Core modification by data — UPG-1

`security/account_groups.xml` rewrites three `res.groups` records owned by `account`, not
`noupdate`. Any `-u account` silently reverts them and the Accounting / Review / Reporting menus
vanish again.

The *intent* is legitimate — Community genuinely leaves those groups unreachable, which is what
made the menus invisible. The debt is the mechanism: a data file that mutates another module's
records, with no test that survives an `account` update.

---

## 8. Tenant architecture that does not exist — SAAS-*

Not debt in the usual sense, but the largest gap: **there is no tenant model, no provisioning, no
offboarding, no routing map.** Tenant identity is a regex over `pg_database` and nothing else.

The specific trap: `db_name = odoo19` currently constrains routing, `list_dbs` **and** cron
simultaneously. Removing it for multi-tenancy opens all three at once (SAAS-1, SAAS-7). That is
the one change most likely to convert a working single-tenant instance into a leaking
multi-tenant one in a single commit.

---

## 9. Vendoring without provenance — DEP-5

Seven OCA modules vendored with **zero local drift** — the "do not edit in place" rule was
honoured, which is exactly what keeps the AGPL modification trigger unpulled. Good discipline.

But provenance is recorded as branch URLs plus a copy date, not commit SHAs, and the documented
update procedure uses `--depth 1` on a moving branch. So there is no way to determine what was
taken, compute drift, reproduce the vendoring, or tell whether an upstream fix has landed —
API-1 is one such fix possibly waiting upstream. Cheap to fix retroactively: record SHAs now.

---

## 10. Documentation drift — DOC-1..4

Six analysis documents at the repo root, at least four materially stale — all written when
`l10n_np_bs` was the only local module, describing a repo one-eighth its current size.

Sharpest example: `NEPAL-ACCOUNTING-BUILD-PLAN.md:3` still reads *"Status: PLAN — no code written
against it yet"* while three of its phases are built and committed **under its own phase names**,
and the file contradicts itself 54 lines later. Every per-module test count in it is wrong.

`README.md` is upstream Odoo's, unmodified — so the project has no entry point at all.

The evidence that these are not being read: two findings `RECONNAISSANCE.md` raised itself
(undeclared `nepali-datetime`, an empty package directory) remain unfixed.

**Debt shape:** point-in-time analysis was treated as living documentation. Several sections
remain accurate and sharp; they need dating and a short maintained README above them.

---

## 11. Environment divergence and naming — CI-2, N-1

Dev and production share no build artefact and are related by prose; the Linux path has never run.
And `l10n_ne/` collides with upstream **Niger**'s localisation (`ne` is Niger; Nepal is `np`,
used correctly everywhere else) — harmless until the repo root joins `addons_path`, then
confusing for an afternoon.

---

## Paydown order

1. **CI-1 + QA-1** — cheapest, and it makes everything after it safer.
2. **Tests that exercise the wrong layer** (§4) — the four correctness fixes each need their test
   fixed *first*, so you can watch it fail and then pass.
3. **UPG-2, UPG-1** — versioning and the core-group hook; FIN-1's migration depends on the first.
4. **DEP-5, N-1, COD-3, COD-2** — small, independent, low-risk.
5. **DOC-1..4** — date the snapshots, write a real README, correct `VENDORED.md` (which LIC-1
   depends on being accurate).
6. **SUP-3** — runbook plus health check now; dissolve later.
7. **SAAS-*** — the tenant architecture, before the second tenant rather than after.
8. **SUP-1 / SUP-4** — the spike. Largest, wrong choice expensive to undo, so last and deliberate.
