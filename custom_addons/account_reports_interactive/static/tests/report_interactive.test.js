/** @odoo-module **/

import { describe, expect, test } from "@odoo/hoot";
import { enhanceReport } from "@account_reports_interactive/report_interactive";

// Headless: these operate on a detached document built here, not on a mounted
// component, so there is nothing to render and no browser chrome to wait for.
describe.current.tags("headless");

/** A stand-in for the report iframe's document, plus a doAction spy. */
function makeReport(html) {
    const doc = document.implementation.createHTMLDocument("report");
    doc.body.innerHTML = html;
    const calls = [];
    const component = {
        env: { services: { action: { doAction: (action) => calls.push(action) } } },
    };
    return { doc, calls, component };
}

const TABLE = `
    <table>
      <tr class="afs-block" data-afs-block="1">
        <td><span class="afs-toggle">▾</span><i>Receivables</i></td>
        <td></td>
      </tr>
      <tr data-afs-line="1">
        <td><span res-id="7" res-model="account.account" view-type="form">1200</span></td>
        <td><span domain="[('account_id','=',7)]" res-model="account.move.line">400</span></td>
      </tr>
      <tr data-afs-line="1">
        <td><span res-id="8" res-model="account.account" view-type="form">1210</span></td>
        <td><span domain="[('account_id','=',8)]" res-model="account.move.line">0</span></td>
      </tr>
      <tr data-afs-subtotal="1">
        <td>Subtotal</td>
        <td><span domain="[('account_type','=','asset_receivable')]" res-model="account.move.line">400</span></td>
      </tr>
    </table>`;

describe("drill-down links", () => {
    test("an amount carrying res-model and domain becomes a link", () => {
        const { doc, component } = makeReport(TABLE);
        enhanceReport(component, doc);

        const amount = doc.querySelector("[domain]");
        expect(amount.parentElement.tagName).toBe("A");
        expect(amount.parentElement.getAttribute("href")).toBe("#");
    });

    test("clicking it opens a filtered list of journal items", async () => {
        const { doc, calls, component } = makeReport(TABLE);
        enhanceReport(component, doc);

        doc.querySelector("[domain]").parentElement.click();

        expect(calls).toHaveLength(1);
        expect(calls[0].type).toBe("ir.actions.act_window");
        expect(calls[0].res_model).toBe("account.move.line");
        expect(calls[0].domain).toBe("[('account_id','=',7)]");
        // list first, so the figure's constituents are what you land on
        expect(calls[0].views[0][1]).toBe("list");
    });

    test("the list view is pinned to the one that shows balance", () => {
        const { doc, calls, component } = makeReport(TABLE);
        enhanceReport(component, doc);
        doc.querySelector("[domain]").parentElement.click();
        // Without this the default journal-items list is used, which hides
        // `balance` -- the one column needed to check the total against the figure.
        expect(calls[0].context.list_view_ref).toBe(
            "account.view_move_line_tree_grouped_general"
        );
    });

    test("running twice does not wrap an element twice", () => {
        // The realistic case, not a theoretical one: OCA's account_financial_report
        // patches the same component with its own [res-model][domain] hook, so on a
        // database with both installed every amount would otherwise get two nested
        // anchors and one click would fire two actions.
        const { doc, calls, component } = makeReport(TABLE);
        enhanceReport(component, doc);
        enhanceReport(component, doc);

        const amount = doc.querySelector("[domain]");
        expect(amount.parentElement.tagName).toBe("A");
        expect(amount.parentElement.parentElement.tagName).not.toBe("A");

        amount.parentElement.click();
        expect(calls).toHaveLength(1);
    });

    test("an element already wrapped by another hook is left alone", () => {
        const { doc, calls, component } = makeReport(TABLE);
        // Simulate OCA's hook having got there first.
        const amount = doc.querySelector("[domain]");
        const theirs = doc.createElement("a");
        amount.parentNode.insertBefore(theirs, amount);
        theirs.appendChild(amount);

        enhanceReport(component, doc);

        expect(amount.parentElement).toBe(theirs);
        amount.parentElement.click();
        expect(calls).toHaveLength(0); // theirs would have handled it
    });

    test("record links are left to core, not duplicated here", () => {
        // Core already wraps [res-id][res-model][view-type]. Wrapping them again
        // would double up on every account code.
        const { doc, component } = makeReport(TABLE);
        enhanceReport(component, doc);
        const code = doc.querySelector("[res-id]");
        expect(code.parentElement.tagName).not.toBe("A");
    });
});

describe("folding", () => {
    test("clicking a block header hides its account lines", () => {
        const { doc, component } = makeReport(TABLE);
        enhanceReport(component, doc);

        const header = doc.querySelector("[data-afs-block]");
        const lines = [...doc.querySelectorAll("[data-afs-line]")];
        expect(lines.map((r) => r.style.display)).toEqual(["", ""]);

        header.click();
        expect(lines.map((r) => r.style.display)).toEqual(["none", "none"]);

        header.click();
        expect(lines.map((r) => r.style.display)).toEqual(["", ""]);
    });

    test("the subtotal stays visible when a block is folded", () => {
        // Folding is for reading a statement at section level; a section whose
        // total vanished with its detail would defeat the point.
        const { doc, component } = makeReport(TABLE);
        enhanceReport(component, doc);

        doc.querySelector("[data-afs-block]").click();
        expect(doc.querySelector("[data-afs-subtotal]").style.display).toBe("");
    });

    test("the arrow reflects the state", () => {
        const { doc, component } = makeReport(TABLE);
        enhanceReport(component, doc);
        const arrow = doc.querySelector(".afs-toggle");
        const header = doc.querySelector("[data-afs-block]");

        expect(arrow.textContent.trim()).toBe("▾");
        header.click();
        expect(arrow.textContent.trim()).toBe("▸");
        header.click();
        expect(arrow.textContent.trim()).toBe("▾");
    });

    test("clicking a drill-down link inside a header does not also fold it", () => {
        const { doc, component } = makeReport(`
            <table>
              <tr class="afs-block" data-afs-block="1">
                <td>
                  <span class="afs-toggle">▾</span>
                  <span domain="[('id','=',1)]" res-model="account.move.line">Total</span>
                </td>
              </tr>
              <tr data-afs-line="1"><td>a line</td></tr>
            </table>`);
        enhanceReport(component, doc);

        doc.querySelector("[domain]").parentElement.click();
        expect(doc.querySelector("[data-afs-line]").style.display).toBe("");
    });

    test("wiring twice does not register two fold handlers", () => {
        const { doc, component } = makeReport(TABLE);
        enhanceReport(component, doc);
        enhanceReport(component, doc);

        const header = doc.querySelector("[data-afs-block]");
        header.click();
        // Two handlers would toggle twice and leave the rows visible.
        expect(doc.querySelector("[data-afs-line]").style.display).toBe("none");
    });
});
