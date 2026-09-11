/** The Matching column widget's state maps.
 *
 * Deliberately narrow. The interesting behaviour of this widget is the mapping
 * from a server-side state to a colour and to "is there anything to open", and
 * that mapping is pure — it needs no mounted view, no model definitions and no
 * RPC mocking to assert, so it is tested directly.
 *
 * What is NOT tested here, and where it is covered instead:
 *   - that each state is computed correctly from the reconciliation data
 *     -> tests/test_matching_column.py, against real partials
 *   - that clicking reaches the counterpart lines
 *     -> test_matching_column.py asserts open_reconcile_view's action resolves
 *        and contains the counterpart, which is the half that can actually be
 *        wrong; whether a click calls it is one line of template.
 *   - that the five states here match the five in Python
 *     -> tests/test_matching_column.py::test_the_javascript_knows_every_state,
 *        which reads this file. A drift check has to live on one side or the
 *        other; it lives in Python because that is where the Selection is
 *        defined.
 */
import { describe, expect, test } from "@odoo/hoot";
import { STATE_STYLE, CLICKABLE } from "@l10n_np_accounting/matching_cell";

describe.current.tags("headless");

test("every state has a class and a glyph", () => {
    for (const [state, style] of Object.entries(STATE_STYLE)) {
        // Boolean(...) then toBe(true): hoot has no toBeTruthy matcher. The
        // first draft used one, and the suite reported it as a failing
        // assertion rather than an unknown method -- worth knowing, because a
        // typo'd matcher name fails loudly here rather than silently passing.
        expect(Boolean(style.className)).toBe(true, {
            message: `${state} has no className, so it would render unstyled`,
        });
        expect(Boolean(style.glyph)).toBe(true, {
            message: `${state} has no glyph`,
        });
    }
});

test("only the states with something to open are clickable", () => {
    // A link that opens nothing is worse than plain text: it invites a click and
    // then does nothing, which reads as a broken page rather than as "no data".
    expect([...CLICKABLE].sort()).toEqual(["matched", "partial"]);

    for (const state of ["open", "pending_post", "not_reconcilable"]) {
        expect(CLICKABLE.has(state)).toBe(false, {
            message: `${state} must not be clickable: open_reconcile_view would `
                + `return an empty list for it`,
        });
    }
});

test("open is the only state drawn as needing attention", () => {
    // A reconcilable line that still owes something is the one actionable state
    // in this column. If more than one state shouted, none of them would.
    const shouting = Object.entries(STATE_STYLE)
        .filter(([, style]) => style.className.includes("warning"))
        .map(([state]) => state);
    expect(shouting).toEqual(["open"]);
});

test("states that are not actionable are muted, not absent", () => {
    // Muted rather than empty, so the column reads as "considered, not
    // applicable" instead of "no data" -- which is the exact conflation this
    // whole change exists to remove.
    for (const state of ["not_reconcilable", "pending_post"]) {
        expect(STATE_STYLE[state].className).toInclude("text-muted", {
            message: `${state} should be muted`,
        });
    }
});
