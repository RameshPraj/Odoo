/** @odoo-module **/

/**
 * Interactive behaviour for HTML financial reports.
 *
 * Two things, both wired from OUTSIDE the report iframe so that nothing needs to
 * be bundled into the rendered document. That matters: the same QWeb template is
 * rendered to PDF, where no JavaScript runs at all, so anything essential has to
 * be in the markup rather than added here. What this file adds is strictly
 * enhancement -- the report is complete and correct without it.
 *
 *   1. `[res-model][domain]` opens a filtered list. Core already handles
 *      `[res-id][res-model][view-type]` for single records
 *      (web/static/src/webclient/actions/reports/report_hook.js), but not the
 *      aggregate case, which is the one a financial statement needs: a total is
 *      not a record, it is a set of them.
 *
 *   2. Account blocks marked `data-afs-block` fold away the `data-afs-line` rows
 *      that follow them, so a statement can be read at section level first.
 */

import { ReportAction } from "@web/webclient/actions/reports/report_action";
import { patch } from "@web/core/utils/patch";
import { useComponent, useEffect } from "@odoo/owl";

const ARROW_OPEN = "▾"; // ▾
const ARROW_SHUT = "▸"; // ▸

/**
 * True when this element has already been turned into a link.
 *
 * OCA's account_financial_report patches the same component with its own
 * `[res-model][domain]` hook, so on a database where both are installed each
 * element would otherwise be wrapped twice, nesting two anchors and firing two
 * actions from one click. The guard also makes re-running safe when the iframe
 * reloads.
 */
function alreadyLinked(element) {
    return (
        element.dataset.ariLinked === "1" ||
        (element.parentElement && element.parentElement.tagName === "A")
    );
}

function linkDomains(component, doc) {
    for (const element of doc.querySelectorAll("[res-model][domain]")) {
        if (alreadyLinked(element)) {
            continue;
        }
        element.dataset.ariLinked = "1";

        const anchor = doc.createElement("a");
        anchor.setAttribute("href", "#");
        anchor.addEventListener("click", (ev) => {
            ev.preventDefault();
            component.env.services.action.doAction({
                type: "ir.actions.act_window",
                name: element.getAttribute("name") || undefined,
                res_model: element.getAttribute("res-model"),
                domain: element.getAttribute("domain"),
                views: [
                    [false, "list"],
                    [false, "form"],
                ],
                // This list view shows `balance` and hides `account_id`, which is
                // the right shape when the figure clicked was already scoped to
                // one account. From there `open_move_widget` on the entry name
                // reaches the account.move form, which is where a correction
                // belongs: debit and credit are balanced there, and the audit
                // trail is intact.
                context: {
                    list_view_ref: "account.view_move_line_tree_grouped_general",
                },
            });
        });
        element.parentNode.insertBefore(anchor, element);
        anchor.appendChild(element);
    }
}

/** The `data-afs-line` rows belonging to a block header. */
function linesUnder(header) {
    const rows = [];
    let row = header.nextElementSibling;
    // Stops at the block's subtotal row, so a folded block still shows its
    // subtotal. Structural rather than by index, because the section template is
    // called once per section and any per-section numbering collides.
    while (row && row.hasAttribute("data-afs-line")) {
        rows.push(row);
        row = row.nextElementSibling;
    }
    return rows;
}

function wireFolding(doc) {
    for (const header of doc.querySelectorAll("[data-afs-block]")) {
        if (header.dataset.ariFold === "1") {
            continue;
        }
        header.dataset.ariFold = "1";

        const arrow = header.querySelector(".afs-toggle");
        if (!arrow) {
            continue;
        }
        // Styled here rather than in a stylesheet because the report renders in
        // an iframe that does not carry this module's assets.
        header.style.cursor = "pointer";
        arrow.style.userSelect = "none";

        header.addEventListener("click", (ev) => {
            // A drill-down link inside the header must not also fold the block.
            if (ev.target.closest("a")) {
                return;
            }
            const shutting = arrow.textContent.trim() !== ARROW_SHUT;
            arrow.textContent = shutting ? ARROW_SHUT : ARROW_OPEN;
            for (const row of linesUnder(header)) {
                row.style.display = shutting ? "none" : "";
            }
        });
    }
}

export function enhanceReport(component, doc) {
    linkDomains(component, doc);
    wireFolding(doc);
}

export function useInteractiveReport(ref) {
    const component = useComponent();
    useEffect(
        (element) => {
            if (!element) {
                return;
            }
            if (element.matches("iframe")) {
                // addEventListener, not `onload =`: core's hook uses the property
                // form, and assigning it here would silently replace theirs.
                element.addEventListener("load", () =>
                    enhanceReport(component, element.contentDocument)
                );
                if (element.contentDocument?.readyState === "complete") {
                    enhanceReport(component, element.contentDocument);
                }
            } else {
                enhanceReport(component, element);
            }
        },
        () => [ref.el]
    );
}

patch(ReportAction.prototype, {
    setup() {
        super.setup(...arguments);
        useInteractiveReport(this.iframe);
    },
});
