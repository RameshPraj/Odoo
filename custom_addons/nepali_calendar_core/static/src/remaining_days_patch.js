/** The Due Date column: the one widget a registry override cannot reach.
 *
 * `account_move_views.xml:536` renders the invoice/bill due date as
 *
 *     <field name="invoice_date_due" widget="remaining_days" .../>
 *
 * An explicit `widget=` makes `canUseFormatter` return false
 * (`list_renderer.js:501-511`), so the cell takes the component route -- but the
 * component it resolves is `remaining_days`, not one of the three date widgets
 * this module replaces. And `RemainingDaysField` imports `formatDate` **statically**
 * (`remaining_days_field.js:9`, used at `:61`), so no entry in the `formatters`
 * registry reaches it either. It is invisible to both of this module's mechanisms,
 * which is why the Due Date column stayed Gregorian after list cells were fixed.
 *
 * A narrow patch of the two getters that produce a date is the whole fix.
 *
 * What is deliberately NOT changed: the relative text. `diffString`
 * (`remaining_days_field.js:42-57`) returns "Today", "In 5 days", "Yesterday" for
 * anything within 99 days, and only falls back to a formatted date beyond that.
 * Those labels are calendar-neutral -- "in 5 days" is the same statement in
 * Bikram Sambat as in Gregorian -- so converting them would add nothing and would
 * lose the at-a-glance overdue signal an accountant actually reads. Only the
 * absolute date underneath becomes BS. The reasoning is recorded in
 * docs/project-review/BIKRAM_SAMBAT.md.
 */
import { patch } from "@web/core/utils/patch";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { RemainingDaysField } from "@web/views/fields/remaining_days/remaining_days_field";
import { adToBs, formatBs } from "./bs_convert";
import { EXCLUDED_FIELDS } from "./exclusions";

const CALENDAR = session.calendar_system || "ad";

/**
 * Bikram Sambat text for a record's date, or null to defer to Odoo.
 *
 * Returns null rather than throwing for anything outside the supported table:
 * showing the Gregorian date is a cosmetic regression, showing a guess is a
 * correctness one.
 */
// Exported for the test suite, following the precedent set by
// `installCalendarOverrides` in registry_overrides.js: the patch below is applied
// at module load, keyed on `session.calendar_system`, which a test cannot change
// after import. Pulling the decision out into a callable function is what made
// that module testable, and this is the same shape -- the rules encoded here (in
// particular the date-vs-datetime zoning guard) are the part worth asserting, not
// the act of patching.
export function bsTextFor(record, name) {
    const value = record.data[name];
    if (!value) {
        return null;
    }
    if (EXCLUDED_FIELDS.has(name)) {
        return null;
    }
    // `invoice_date_due` is a Date, not a Datetime, so there is no instant and no
    // timezone normalisation to do -- re-zoning it would invent one and shift the
    // day for anyone west of UTC. The guard keeps that true if the widget is ever
    // pointed at a Datetime field.
    const local =
        record.fields[name] && record.fields[name].type === "datetime"
            ? value.setZone(user.tz || "default")
            : value;
    try {
        return formatBs(adToBs(local.year, local.month, local.day), {
            npDigits: session.bs_digits === "devanagari",
        });
    } catch {
        return null;
    }
}

if (CALENDAR === "bs") {
    patch(RemainingDaysField.prototype, {
        get formattedValue() {
            const text = bsTextFor(this.props.record, this.props.name);
            if (text === null) {
                return super.formattedValue;
            }
            return text;
        },

        get numericValue() {
            // Used for the cell's `title` tooltip. Keep it in step with the
            // visible value, or hovering would contradict what is on screen.
            const text = bsTextFor(this.props.record, this.props.name);
            if (text === null) {
                return super.numericValue;
            }
            return text;
        },
    });
}
