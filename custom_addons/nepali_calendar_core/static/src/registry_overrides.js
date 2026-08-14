/** Make every date field follow the user's calendar preference.
 *
 * Odoo 19 has ONE component behind the `date`, `datetime` and `daterange` field
 * widgets (`DateTimeField`), and form views, list cells and kanban cards all
 * render through it. Replacing that component covers all three in a single place
 * -- no per-model registration, no field enumeration, and nothing to keep in step
 * as modules are installed.
 *
 * Why not mutate view architecture instead (the approach this replaced):
 * `_get_view_cache` returns an arch shared between users whose default cache key
 * contains **no uid**. Keying a widget swap on a per-user preference through that
 * path leaks one user's calendar into another user's form unless the cache key is
 * also extended. Going through the registry avoids the question entirely, and
 * costs no server work at all.
 *
 * Why the `formatters` registry is deliberately NOT overridden: `DateTimeField`
 * imports `formatDate` **statically** from `@web/views/fields/formatters`, so a
 * registry entry would not affect field rendering at all. The registry is used for
 * list *aggregates*, and that call site passes no field metadata
 * (`list_renderer.js:767-770` supplies only `digits`/`escape`/`currencyId`), so
 * exclusions could not be honoured there. Overriding it would buy nothing and
 * would silently ignore the exclusion list.
 *
 * `force: true` is the documented way to replace an existing registry entry.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { user } from "@web/core/user";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { BSDateField } from "./bs_date_field";
import { isExcluded } from "./exclusions";
import { bsToAd, parseBs } from "./bs_convert";

const fields = registry.category("fields");
const parsers = registry.category("parsers");

// Resolved server-side as user -> company -> AD and shipped in `session_info`.
// Read once at module load: changing the preference triggers Odoo's own
// `reload_context` client action, so there is no live-switch case to handle.
const CALENDAR = session.calendar_system || "ad";

/**
 * Chooses per field whether to render Bikram Sambat or hand off to Odoo's own
 * widget. The dispatch has to happen at render time rather than at registration
 * time, because the exclusion decision depends on the record's model and the
 * field's name -- neither of which is known when the registry is populated.
 */
export class CalendarAwareDateField extends Component {
    static template = "nepali_calendar_core.CalendarAwareDateField";
    static props = { ...standardFieldProps, "*": true };
    static components = { BSDateField };

    /** The native component this override displaced, resolved lazily. */
    static nativeComponents = {};

    get useBS() {
        return !isExcluded(this.props.record?.resModel, this.props.name);
    }

    get NativeComponent() {
        return CalendarAwareDateField.nativeComponents[this.props.__nativeWidget__];
    }
}

if (CALENDAR === "bs") {
    for (const name of ["date", "datetime", "daterange"]) {
        const native = fields.get(name, null);
        if (!native) {
            // A future Odoo could rename these. Leaving Gregorian in place is the
            // correct failure mode: English dates are a cosmetic regression,
            // whereas wrong dates are a correctness one.
            continue;
        }
        CalendarAwareDateField.nativeComponents[name] = native.component;
        CalendarAwareDateField.components[`Native_${name}`] = native.component;

        fields.add(
            name,
            {
                ...native,
                component: CalendarAwareDateField,
                extractProps: (fieldInfo, dynamicInfo) => ({
                    // Preserve whatever the native descriptor extracts, so options
                    // already written into existing views keep working.
                    ...(native.extractProps
                        ? native.extractProps(fieldInfo, dynamicInfo)
                        : {}),
                    // Which native component to fall back to when excluded.
                    __nativeWidget__: name,
                    npDigits: session.bs_digits === "devanagari",
                }),
            },
            { force: true }
        );
    }

    // -- parsers ------------------------------------------------------------
    // Typed input, including the search bar. A BS date is tried first; anything
    // else falls through to Odoo's parser, so a user can still type a Gregorian
    // date, a relative expression like `+1w`, or `today`.
    for (const name of ["date", "datetime"]) {
        const nativeParse = parsers.get(name);
        parsers.add(
            name,
            (value, options = {}) => {
                const bs = parseBs(value);
                if (bs) {
                    try {
                        const ad = bsToAd(bs.year, bs.month, bs.day);
                        // Build the instant in the user's zone for a datetime, so
                        // the stored UTC value lands on the day the user meant.
                        // `user.tz` rather than `session.user_context.tz`: same
                        // value, but it is the accessor `bs_date_field.js` uses,
                        // and one source avoids the two drifting.
                        const zone =
                            name === "datetime" ? user.tz || "default" : "default";
                        return luxon.DateTime.fromObject(
                            { year: ad.year, month: ad.month, day: ad.day },
                            { zone }
                        );
                    } catch {
                        // Valid shape, impossible date -- let the native parser
                        // produce the error the user expects.
                    }
                }
                return nativeParse(value, options);
            },
            { force: true }
        );
    }
}
