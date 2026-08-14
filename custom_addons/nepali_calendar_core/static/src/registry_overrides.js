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
//
// Read from `session` directly rather than through a service. A `nepali_calendar`
// service was written for this and then deleted: registry overrides run at module
// import, which is *before* any service has started, so a service cannot answer
// the one question that has to be answered here. Keeping an accessor that no
// caller could use would have been a decorative abstraction.
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

    /**
     * Props for the BS widget: everything except our own routing prop.
     *
     * The two synthetic props MUST be stripped before forwarding. Owl validates
     * props strictly, and both `BSDateField` and Odoo's `DateTimeField` reject
     * anything they do not declare -- so passing the whole bag straight through
     * raised `OwlError: Invalid props` and took out the field. `BSDateField` also
     * carries `"*": true` for the reverse case: the native descriptor's
     * `extractProps` emits options like `warnFuture` and `maxDate` that mean
     * nothing to a BS widget but must not be an error either.
     */
    get bsProps() {
        const { __nativeWidget__, ...rest } = this.props;
        return rest;
    }

    /** Props for Odoo's own widget: also without the digit style, which is ours. */
    get nativeProps() {
        const { __nativeWidget__, npDigits, ...rest } = this.props;
        return rest;
    }
}

/** Field widget names that render a date and must follow the preference. */
export const OVERRIDDEN_FIELDS = ["date", "datetime", "daterange"];

/** Parser names for typed date input, including the search bar. */
export const OVERRIDDEN_PARSERS = ["date", "datetime"];

/**
 * Point the date registries at the calendar-aware wrappers.
 *
 * Exported and **idempotent** rather than inlined at module scope, for one
 * reason: it makes the *selection* testable. The module-load call below reads
 * `session`, which a test cannot change after import -- so without this function
 * a test could verify the exclusion predicate and verify that BSDateField
 * renders, but never that a bare `<field name="invoice_date"/>` actually picks
 * BSDateField while `create_date` does not. That composition is the whole
 * coverage model, and it was the largest untested gap in this module.
 *
 * Idempotent because it re-reads the native descriptor from
 * `CalendarAwareDateField.nativeComponents` when it has already displaced one;
 * calling it twice must not make the wrapper wrap itself, which would recurse
 * forever at render time.
 *
 * @param {string} calendar "ad" | "bs". Anything but "bs" is a no-op, so an AD
 *   user's client is byte-identical to one without this module installed.
 * @param {object} [deps] injectable registries, for tests
 * @returns {string[]} the widget names actually overridden
 */
export function installCalendarOverrides(calendar, deps = {}) {
    const fieldsRegistry = deps.fields || fields;
    const parsersRegistry = deps.parsers || parsers;
    const npDigits = (deps.npDigits ?? session.bs_digits) === "devanagari";
    const installed = [];

    if (calendar !== "bs") {
        return installed;
    }

    for (const name of OVERRIDDEN_FIELDS) {
        const current = fieldsRegistry.get(name, null);
        if (!current) {
            // A future Odoo could rename these. Leaving Gregorian in place is the
            // correct failure mode: English dates are a cosmetic regression,
            // whereas wrong dates are a correctness one.
            continue;
        }
        // If we already displaced this entry, the native component is the one we
        // stashed -- not the wrapper currently in the registry.
        const native =
            current.component === CalendarAwareDateField
                ? { ...current, component: CalendarAwareDateField.nativeComponents[name] }
                : current;

        CalendarAwareDateField.nativeComponents[name] = native.component;

        fieldsRegistry.add(
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
                    npDigits,
                }),
            },
            { force: true }
        );
        installed.push(name);
    }

    // -- parsers ------------------------------------------------------------
    // Typed input, including the search bar. A BS date is tried first; anything
    // else falls through to Odoo's parser, so a user can still type a Gregorian
    // date, a relative expression like `+1w`, or `today`.
    for (const name of OVERRIDDEN_PARSERS) {
        const nativeParse = parsersRegistry.get(name);
        if (nativeParse?.__isBsParser__) {
            continue;   // already installed
        }
        const bsParse = (value, options = {}) => {
            const bs = parseBs(value);
            if (bs) {
                try {
                    const ad = bsToAd(bs.year, bs.month, bs.day);
                    // Build the instant in the user's zone for a datetime, so the
                    // stored UTC value lands on the day the user meant. `user.tz`
                    // rather than `session.user_context.tz`: same value, but it is
                    // the accessor `bs_date_field.js` uses, and one source avoids
                    // the two drifting.
                    const zone = name === "datetime" ? user.tz || "default" : "default";
                    return luxon.DateTime.fromObject(
                        { year: ad.year, month: ad.month, day: ad.day },
                        { zone }
                    );
                } catch {
                    // Valid shape, impossible date -- let the native parser produce
                    // the error the user expects.
                }
            }
            return nativeParse(value, options);
        };
        bsParse.__isBsParser__ = true;
        parsersRegistry.add(name, bsParse, { force: true });
    }

    return installed;
}

installCalendarOverrides(CALENDAR);
