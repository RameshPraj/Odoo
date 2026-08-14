# Code Review

Findings referenced by ID; full evidence in [`BACKLOG.md`](BACKLOG.md).

## Overall

**The locally written code is good.** It is idiomatic Odoo 19 with no API rot, carries unusually
informative comments, and several design decisions are both correct and deliberately explained.
The defects are concentrated in *data wiring* and *test placement*, not in the code itself.

A representative measure: across all eight local modules there are **zero** occurrences of
`_sql_constraints`, `@api.one`, `@api.multi`, `attrs=`, `states=`, `<tree>`, `name_get` or the old
`Many2many` signature — every one of which is either removed or deprecated in Odoo 19.
`models.Constraint` is used correctly in eight places, and `l10n_np_tds/models/tds_category.py:79-81`
carries a comment explaining precisely why the migration was necessary (a legacy
`_sql_constraints` list is *silently ignored*, so the check would never reach the database). That
is the difference between code that happens to work and code someone understood.

## The one correctness defect — FIN-1

Not a coding error but a data-wiring omission, and the most consequential finding in the audit.

`l10n_np` defines 8 tax tags and 3 sale taxes with 12 repartition lines. **Nothing joins them** —
`account_account_tag_account_tax_repartition_line_rel` has 0 rows database-wide. Since
`l10n_np_vat_return` derives every box from tax tags, every box evaluates to zero.

The module's design is otherwise sound: boxes are configurable records, forms are versioned, and
a filed return freezes the form it was computed against so a reprint cannot drift. The gap is one
missing association in the chart template.

## Per-module notes

### `l10n_np_loan` — the strongest module
22 tests, and the amortisation engine is genuinely correct. The design decision that makes it so
is worth recording: **the final instalment repays whatever principal remains** rather than a
recomputed figure, which is what lands the closing balance on exactly zero under any method, rate
and rounding. The alternative leaves a few paisa on the liability account that nobody can clear.
The engine also refuses, with a sentence, a rate so high the payment never covers interest —
rather than producing a schedule that grows forever.

The period rate is a simple annual/periods division rather than an effective-rate conversion,
with a comment explaining that this matches how Nepali bank sanction letters quote it. Matching
the lender's arithmetic over compounding purity is the right call and it is documented.

Issues: float `assertEqual` on money throughout the tests (COD-1), `assertRaises(Exception)`
(COD-7), one time-dependent test (TST-6).

### `l10n_np_vat_return`
Well-structured. The formula evaluator correctly blocks RCE — verified, and tested. Two issues:
the whitelist admits `**` (SEC-3, one-character fix), and the ACL grants the read-only accounting
role write/create/unlink on return lines (SEC-6), inconsistent with the same file's own rows for
the form and box.

### `l10n_np_tds`
The rate schedule is properly versioned with date ranges and a clear error naming the menu to fix
it. The weakness is `action_collect_lines` (TST-5, COD-5): it duck-types against
`account.withholding.line` with `getattr(line, 'base_amount', 0.0)` and `'partner_id' in
l._fields`, justified by a comment about field names differing across versions. Against a pinned,
vendored Odoo tree that justification does not hold, the branches are unreachable in one
direction and untested in both, and the failure mode is a certificate reporting **zero withheld**
with no error.

### `l10n_np_bs`
The Python side is clean and the conversion is verified across the full supported range. The
problem is duplication: the JavaScript is a **second, independent implementation** of AD↔BS
conversion, and `tools/selftest.py` — which exists precisely to cross-check the generated table —
is invoked by nothing (TST-4). Also uses a private library symbol (COD-10).

### `l10n_np_accounting`
The most runtime-invasive module, and correctly built. Overriding `_get_view` to inject the BS
date widget across an allowlist of fields is the same seam core uses for `res.currency`, and
`_get_view_cache_key` is properly extended so two users who disagree about the setting cannot be
served each other's arch. The reasoning for choosing this over view inheritance — that
`account.view_move_form` carries two `invoice_date` nodes and a name-based xpath silently patches
only the first — is documented in the module.

The Reconcile button is a thin, well-guarded shell over Community's own public `reconcile()`,
turning tracebacks into sentences. The Lock Dates wizard correctly leaves hard-lock
irreversibility to core and uses a precomputed stored compute rather than `default_get`, with a
comment explaining that `default_get` cannot see `create()` vals and would otherwise load the
wrong company's locks.

### `account_financial_statements`
Balance Sheet ties (period result added to equity), Cash Flow is self-proving. Weakness is test
coupling to live database state (TST-2).

### `l10n_np`, `l10n_np_fiscal_year`
`l10n_np_fiscal_year` is the only module with proper test fixtures — it creates its own company,
with a comment recording that this was changed after the bug bit (`82f3ee43`). That fix was never
propagated to the other seven modules (TST-2).

## Duplication

| ID | What | Where |
|---|---|---|
| COD-2 | `test_xml_is_well_formed` copy-pasted **5×**, absent from 3 of 8 modules. Four copies use `minidom`, which accepts `--` in comments where Odoo's `lxml` rejects it — so those four cannot catch the defect they exist for | 5 test files |
| TST-4 | Two independent AD↔BS implementations, no cross-check | `tools/bs.py` vs `static/src/bs_convert.js` |
| COD-8 | Menu-tree walker written out three times **in one file** | `test_menu_visibility.py:24-32,92-104,129-141` |
| COD-9 | "date_from precedes date_to" reimplemented four times with four different messages | 4 modules |

COD-2 is the instructive one: four commits in the project's history are fixes for malformed XML
blanking the backend, the tests were written *after* being burned repeatedly, and copy-paste
instead of a shared mixin is exactly why three modules were missed and why four of the five
copies use the wrong parser.

## Dead and defensive code

- **COD-3** — three empty package directories shipped (`l10n_np_bs/models/`,
  `l10n_np_bs/static/tests/`, `l10n_np_fiscal_year/models/`). Git does not track empty
  directories, so `git clone` produces a different tree from the working copy — and
  `static/tests/`, the location the manifest declares a test bundle for, silently does not exist
  on a fresh clone. Flagged at `RECONNAISSANCE.md:487` and never actioned.
- **PKG-1** — the corresponding asset glob matches nothing.
- **COD-5** — defensive duck-typing against a pinned tree (see `l10n_np_tds` above).
- **COD-6** — broad `except Exception` in four production paths, discarding tracebacks behind a
  generic `UserError`. `bs.py:75,89` wraps the library call the whole calendar depends on.
- **`tools/selftest.py`** — working verification code that nothing runs.

## Maintainability

- **COD-4** — all eight modules frozen at `19.0.1.0.0` across 28 commits, including
  substantially rewritten ones. Odoo triggers upgrades on version increase, so a static version
  means deploying new code requires a remembered `-u`; otherwise the database keeps old views,
  menus and **ACLs** while the source tree has moved on. That makes it a correctness concern, not
  just hygiene.
- **QA-1** — `# noqa` suppressions scattered through the code with no linter configured to read
  them. `# noqa: S307` on a live `eval()` reads as a dismissed security warning with nothing
  re-checking it.
- **QA-2** — UTF-8 BOM in six files.
- **DOC-5** — **zero** TODO/FIXME/HACK/XXX in local code, which is genuinely good. But deferred
  work lives in prose instead, so grepping the code returns a false all-clear. See
  [`TODO_REGISTER.md`](TODO_REGISTER.md).

## What not to change

Do not "fix" findings inside vendored OCA modules in place (SEC-4, SEC-5, SEC-8, SEC-9, API-1).
Those modules currently have **zero local drift**, which is what keeps the AGPL modification
trigger unpulled (LIC-1) and what makes re-syncing upstream possible at all. Override locally or
report upstream.
