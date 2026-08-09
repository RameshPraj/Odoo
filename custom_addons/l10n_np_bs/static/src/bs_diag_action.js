/** Diagnostic client actions -- isolate plumbing failures from markup failures.
 *
 * Two deliberately trivial actions:
 *   l10n_np_bs.diag_plain   bare <div>, no Layout, no imports beyond OWL
 *   l10n_np_bs.diag_layout  same content wrapped in <Layout>
 *
 * If BOTH render, the action/asset plumbing is fine and any blank page is
 * caused by the calendar's own markup or logic.
 * If only `plain` renders, the problem is how Layout is being used.
 * If NEITHER renders, the problem is action registration or asset delivery.
 *
 * Remove this file (and its menu items) once the calendar is confirmed working.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Layout } from "@web/search/layout";
import { adToBs, formatBs } from "./bs_convert";

class BSDiagBase extends Component {
    static props = { ...standardActionServiceProps };

    /** Exercise the conversion layer too, so a throw here is visible. */
    get probe() {
        try {
            const n = new Date();
            const bs = adToBs(n.getFullYear(), n.getMonth() + 1, n.getDate());
            return `conversion OK -> ${formatBs(bs, { monthName: true })}`;
        } catch (e) {
            return `conversion FAILED: ${e.message}`;
        }
    }
}

export class BSDiagPlain extends BSDiagBase {
    static template = "l10n_np_bs.DiagPlain";
}

export class BSDiagLayout extends BSDiagBase {
    static template = "l10n_np_bs.DiagLayout";
    static components = { Layout };
    setup() {
        this.display = { controlPanel: {} };
    }
}

registry.category("actions").add("l10n_np_bs.diag_plain", BSDiagPlain);
registry.category("actions").add("l10n_np_bs.diag_layout", BSDiagLayout);
