# Interactive Financial Reports

Makes the HTML financial reports drillable and foldable: click a figure and you get
the journal items behind it, open one and you can correct it. Printing is unaffected.

## Why this is so small

Almost all of the drill-down already exists in Odoo and nobody uses it.

`ReportAction` — the client action that displays any `qweb-html` report — calls
`useEnrichWithActionLinks` on its iframe
(`web/static/src/webclient/actions/reports/report_action.js:37`). That hook walks the
rendered document for elements carrying `res-id`, `res-model` and `view-type`, and
wraps each one in a link that opens that record
(`.../reports/report_hook.js:47`). So a report template can make any cell
clickable with three attributes and no JavaScript whatsoever.

What core does **not** do is the aggregate case, which is the one a financial
statement needs: a total is not a record, it is a set of them. This module adds that
half — an element carrying `res-model` and `domain` opens a filtered list — by
patching the same component.

That is the entire mechanism. There is no bespoke report component here, and
deliberately so: see "Why not a custom OWL view" below.

## What it does

| Attribute pattern | Behaviour | Provided by |
|---|---|---|
| `res-id` + `res-model` + `view-type` | opens that one record | **Odoo core** |
| `res-model` + `domain` | opens a list filtered by the domain | this module |
| `data-afs-block` / `data-afs-line` | fold a block's detail away | this module |

The drill-down opens `account.move.line` pinned to
`account.view_move_line_tree_grouped_general`, which shows `balance` and hides
`account_id` — the right shape when the figure you clicked was already scoped to one
account, and the column you need to check the list total against the figure. From
there the entry name carries `open_move_widget`, which reaches the `account.move`
form. Corrections belong there rather than in an editable line list: debit and credit
are balanced together on the move, and the audit trail stays intact.

## Why not a custom OWL view

A standalone component was the obvious approach and would have been worse. The
report is rendered server-side from QWeb, and the *same template* is rendered to
PDF. Because the drill-down is attributes, and attributes are inert without
JavaScript, the screen and the printout are the same document — they cannot drift.
A bespoke interactive view would have needed its own parallel print path, and
keeping two renderings of the same statement in agreement forever is precisely the
bug this feature exists to help people find.

The cost of that choice is honest: there is no in-page re-filtering. Changing dates
means going back through the wizard, because the HTML is server-rendered. For a
financial statement that is an acceptable trade; for a dashboard it would not be.

## Coexisting with OCA's version of the same hook

`account_financial_report` patches `ReportAction` with its own `[res-model][domain]`
hook, and applies it to *every* report rather than only its own
(`report_action.esm.js:13`). So on a database with both installed, two hooks walk the
same document. Ours skips anything already wrapped in an anchor; without that guard
every amount would get two nested links and one click would fire two actions. There
is a test for exactly that.

We keep our own copy rather than depending on theirs so the statements still work if
that module is ever uninstalled, and because theirs is AGPL-3 — this is written
against core's contract, not copied.

## The OCA repairs

`report/oca_drilldown_overlays.xml` fixes drill-down in the vendored reports **from
the outside**, by QWeb inheritance. `custom_addons/VENDORED.md` forbids editing those
modules in place, and the reason is not tidiness: `account_financial_report` is
AGPL-3, so modifying it while serving it over a network triggers the publication
clause. Overriding leaves their files byte-identical to upstream, so the next sync
stays a straight copy.

**Aged Partner Balance could not render at all** (**FIN-3**). Its wizard passed
`date_at` as a `date` while the report called `strptime` on it, so every Export raised
`TypeError`. Fixed by a wizard override in `models/`, since a QWeb overlay cannot
reach Python. Its own tests pass because they call `_get_report_values` with a
hand-built string and never traverse the wizard — the same pattern as FIN-2 earlier in
this project, and the reason nobody had noticed the next item either: you could not
reach the page to click anything.

**Aged Partner Balance drill-down** had eight amounts written `domain="…"` instead of
`t-att-domain="…"`. Without the `t-att-` prefix QWeb never evaluates the expression;
it copies the Python source text into the HTML attribute, and the JavaScript then
hands that text to `doAction` as a domain. The expressions were fine and are reused
unchanged. Note these live in the move-line detail template, which renders only when
`show_move_line_details` is on — a test without that flag exercises none of it.

**Open Items and Journal Ledger had no amount-level drill-down at all.** Added on the
figures that are aggregates: Open Items' ending balances, and Journal Ledger's per-journal
debit and credit totals.

Both build their domains from **the ids the report already selected**, not from a
reconstructed filter, and that is not a style preference. "Open items as at a date" is
a function of reconciliation history, so a line's residual as at a past `date_at` is
not its current `amount_residual` — a plausible-looking
`[('amount_residual','!=',0)]` would quietly disagree with the printed figure whenever
the date is in the past, which is most of the time this report is run. Journal totals
depend on wizard filters that a hand-written domain would have to track forever. A test
asserts the journal totals equal the summed debit/credit of the lines their links open.

Per-line amounts are deliberately left alone: each is a single move line, and the row
already links its entry to the `account.move` form. A domain there would open a
one-row list, which is strictly worse.

## Tests

- `tests/test_oca_overlays.py` asserts on the **combined** arch, not on our file:
  what matters is what Odoo produced after inheritance. It also asserts the vendored
  template still contains its original broken markup, which is how we know the fix
  really is an overlay and nobody edited the AGPL-3 module in place.
- `static/tests/report_interactive.test.js` — 11 hoot tests covering the link
  wrapping, the action payload, folding, and the double-wrap guard. Run from Python
  by `tests/test_js_unit.py`; a `.test.js` file missing from its `SUITES` list fails
  that suite rather than being silently skipped.

The figure-to-drill-down agreement itself is tested where the figures are computed,
in `account_financial_statements/tests/test_financial_statements.py`.
