/** Resolves the active calendar for the browser session.
 *
 * The value is computed server-side (user -> company -> AD) and shipped in
 * `session_info`, so this service only reads it. Nothing here queries.
 *
 * Why a service rather than reading `session` directly at each call site: the
 * widget, the formatters and the parsers all need the same answer, and a single
 * accessor keeps the "is BS active" decision in one place.
 */
import { registry } from "@web/core/registry";
import { session } from "@web/session";

export const calendarService = {
    start() {
        // `session_info` supplies these; both have safe fallbacks so the widget
        // degrades to Gregorian rather than throwing if the keys are absent
        // (e.g. an older session, or the frontend bundle where session_info is
        // the reduced `get_frontend_session_info`).
        const system = session.calendar_system || "ad";
        const digits = session.bs_digits || "latin";
        return {
            /** "ad" | "bs" */
            get system() {
                return system;
            },
            get isBS() {
                return system === "bs";
            },
            /** true when Devanagari numerals are wanted */
            get npDigits() {
                return digits === "devanagari";
            },
        };
    },
};

registry.category("services").add("nepali_calendar", calendarService);
