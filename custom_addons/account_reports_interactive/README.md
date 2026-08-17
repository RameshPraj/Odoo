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

**Aged Partner Balance** had eight amounts written `domain="…"` instead of
`t-att-domain="…"`. Without the `t-att-` prefix QWeb never evaluates the expression;
it copies the Python source text into the HTML attribute, and the JavaScript then
hands that text to `doAction` as a domain. That drill-down has never worked, on any
version, while looking entirely present in the source. The expressions were fine and
are reused unchanged.

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
