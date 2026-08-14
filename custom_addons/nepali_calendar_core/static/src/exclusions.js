/** Date fields that must stay Gregorian even for a BS user.
 *
 * Coverage is global by default, so this list is the whole coverage policy. It is
 * short on purpose: of the 1,223 stored date/datetime fields in a typical
 * database, 961 are the `create_date`/`write_date` audit pair and ~26 more are
 * technical, leaving ~237 genuine business dates. Excluding the noise is cheaper
 * and far more maintainable than enumerating the signal.
 *
 * Rule of thumb for adding an entry: if a *machine* reads the value, or if the
 * value records when a row was touched rather than when something happened in the
 * business, it belongs here.
 */

/** Field names excluded on every model. */
export const EXCLUDED_FIELDS = new Set([
    // The ORM audit pair. Present on nearly every model; almost never a business
    // date, and users cross-reference them with server logs, which are AD.
    "create_date",
    "write_date",
    // Scheduler internals.
    "nextcall",
    "lastcall",
    // "Last seen / last synced" style technical stamps.
    "last_modified_date",
    "date_automation_last",
    "last_data_change",
    "calendar_last_notif_ack",
    "visit_datetime",
    "last_connection_datetime",
]);

/** Models whose dates are entirely technical. Prefix match on the model name. */
export const EXCLUDED_MODEL_PREFIXES = [
    "ir.cron",
    "ir.config",
    "ir.module",
    "ir.logging",
    "ir.attachment",
    "ir.actions",
    "bus.",
    "res.device",
    "website.track",
    "website.visitor",
];

/** Specific (model, field) pairs, where the model is otherwise in scope. */
export const EXCLUDED_PAIRS = new Set([
    // Mail internals are technical, but mail.activity.date_deadline is a real
    // user-facing due date, so the model cannot be excluded wholesale.
    "mail.message/date",
    "mail.tracking.value/create_date",
    "mail.notification/read_date",
]);

/**
 * @param {string} resModel
 * @param {string} fieldName
 * @returns {boolean} true when this field must render Gregorian regardless of preference
 */
export function isExcluded(resModel, fieldName) {
    if (EXCLUDED_FIELDS.has(fieldName)) {
        return true;
    }
    if (resModel) {
        if (EXCLUDED_PAIRS.has(`${resModel}/${fieldName}`)) {
            return true;
        }
        for (const prefix of EXCLUDED_MODEL_PREFIXES) {
            if (resModel.startsWith(prefix)) {
                return true;
            }
        }
    }
    return false;
}
