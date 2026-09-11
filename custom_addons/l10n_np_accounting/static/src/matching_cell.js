/** `account_matching` field widget -- the Matching column on Journal Items.
 *
 *     <field name="matching_label" widget="account_matching"/>
 *
 * Core renders `matching_number` as plain text, which on a real database means a
 * bare `account.full.reconcile` primary key such as `37` on a few rows and blank
 * on the rest. The blanks are the worse half: "this account can never be
 * reconciled" and "this is reconcilable and still owed" look identical.
 *
 * This draws `matching_label` (the sentence, computed server-side so it also
 * exports) coloured by `matching_status`, and makes the matched and partial cells
 * open the counterpart journal items.
 *
 * The label is computed on the server rather than assembled here on purpose: an
 * XLSX export and a printed list read the same field, so the information cannot
 * exist only on screen. This widget adds colour and a click; it is not the
 * source of truth.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/** Badge class and leading glyph per state.
 *
 * `open` is the only actionable state in this column -- a reconcilable line that
 * still owes something -- so it is the only one that gets a warning colour.
 * `not_reconcilable` is muted rather than absent so the column reads as
 * "considered, not applicable" instead of "no data".
 */
export const STATE_STYLE = {
    matched: { className: "text-success", glyph: "✓" },
    partial: { className: "text-info", glyph: "◑" },
    open: { className: "text-warning fw-bold", glyph: "●" },
    pending_post: { className: "text-muted fst-italic", glyph: "⏱" },
    not_reconcilable: { className: "text-muted", glyph: "—" },
};

/** States where there is something to open. */
export const CLICKABLE = new Set(["matched", "partial"]);

export class MatchingCell extends Component {
    static template = "l10n_np_accounting.MatchingCell";
    static props = { ...standardFieldProps };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
    }

    get status() {
        // `matching_status` has to be in the view for this to resolve. The view
        // adds it as column_invisible, and `not_reconcilable` is the safe
        // fallback: muted and not clickable.
        return this.props.record.data.matching_status || "not_reconcilable";
    }

    get style() {
        return STATE_STYLE[this.status] || STATE_STYLE.not_reconcilable;
    }

    get label() {
        return this.props.record.data[this.props.name] || "";
    }

    get isClickable() {
        return CLICKABLE.has(this.status);
    }

    get title() {
        if (this.isClickable) {
            return _t("Show the journal items this line is matched against");
        }
        if (this.status === "open") {
            return _t("Reconcilable and still open. Nothing is matched yet.");
        }
        if (this.status === "pending_post") {
            return _t("Marked to be matched once its entries are posted.");
        }
        return _t("This account does not allow reconciliation.");
    }

    /** Open the counterpart lines.
     *
     * Calls core's own `open_reconcile_view` rather than building an action here.
     * It already resolves the whole match through `_all_reconciled_lines()`,
     * including lines joined through several partials, and it already skips the
     * `I` markers that are not really matched. Duplicating that domain in
     * JavaScript would be a second definition of "the same match", free to drift
     * from the server's.
     */
    async onClick(ev) {
        if (!this.isClickable) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const action = await this.orm.call(
            this.props.record.resModel,
            "open_reconcile_view",
            [[this.props.record.resId]],
        );
        this.action.doAction(action);
    }
}

export const matchingCell = {
    component: MatchingCell,
    displayName: _t("Matching state"),
    supportedTypes: ["char"],
};

registry.category("fields").add("account_matching", matchingCell);
