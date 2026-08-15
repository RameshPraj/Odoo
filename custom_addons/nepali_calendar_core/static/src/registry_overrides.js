/** Make every date field follow the user's calendar preference.
 *
 * Odoo 19 renders a date in a user-facing view by exactly TWO routes, and both
 * have to be covered. Getting this wrong is what made Bikram Sambat work in form
 * views while invoice *lists* stayed Gregorian.
 *
 *   1. The `fields` registry -- a real Owl component. Used by form views always,
 *      and by a list column ONLY when the arch sets an explicit `widget=`.
 *   2. The `formatters` registry -- a plain string, no component at all. This is
 *      the path a readonly list cell and a kanban card take.
 *
 * Route 2 is the one that matters most by volume, and it is easy to miss because
 * it never instantiates anything:
 *
 *     list_renderer.xml:299   <t t-if="canUseFormatter(column, record)"
 *                                 t-out="getFormattedValue(column, record)"/>
 *     list_renderer.xml:300   <Field t-else="" .../>
 *
 * `canUseFormatter` (list_renderer.js:501-511) is true for any column without a
 * `widget=` on a row that is not being edited, and `getFormattedValue` resolves
 * through `views/utils.js:139-151` to `formatters.get(field.type)`. Kanban does
 * the same at `kanban_record.js:216-219`.
 *
 * > Correction, recorded rather than quietly amended. This comment previously
 * > claimed the `formatters` registry was used only for list *aggregates* and
 * > carried no field metadata, and concluded that overriding it "would buy
 * > nothing". Both halves were wrong -- it is the primary readonly-cell path, and
 * > `views/utils.js:146-147` passes `data` and `field`. That mistake is precisely
 * > why list views kept showing Gregorian dates.
 *
 * What the formatter route cannot do is see the *model*: `getFormattedValue`
 * passes the field descriptor but not the record, so exclusions there are by
 * field NAME only. That covers `create_date`/`write_date` and the other technical
 * names, which is the overwhelming majority; model-scoped pairs like
 * `mail.message/date` apply on the component route only. Documented in
 * docs/project-review/BIKRAM_SAMBAT.md rather than silently accepted.
 *
 * Why not mutate view architecture instead (the approach this replaced):
 * `_get_view_cache` returns an arch shared between users whose default cache key
 * contains **no uid**. Keying a widget swap on a per-user preference through that
 * path leaks one user's calendar into another user's form unless the cache key is
 * also extended. Going through the registries avoids the question entirely, and
 * costs no server work at all.
 *
 * `force: true` is the documented way to replace an existing registry entry.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { user } from "@web/core/user";
import { localization } from "@web/core/l10n/localization";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { BSDateField } from "./bs_date_field";
import { EXCLUDED_FIELDS, isExcluded } from "./exclusions";
import { adToBs, bsToAd, formatBs, parseBs } from "./bs_convert";

const fields = registry.category("fields");
const parsers = registry.category("parsers");
const formatters = registry.category("formatters");

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
 * Formatter names for the readonly render path.
 *
 * Only `date` and `datetime` exist upstream (`formatters.js:462-463`); there is
 * deliberately no `daterange` formatter, because a daterange column is a plain
 * date/datetime ORM field and only becomes a component when the arch asks for
 * `widget="daterange"`.
 */
export const OVERRIDDEN_FORMATTERS = ["date", "datetime"];

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

    // -- formatters ----------------------------------------------------------
    // The readonly path: list cells, kanban cards and column aggregates. No
    // component is involved, so this is the only way to reach them. See the
    // header comment for why this was missed the first time.
    const formattersRegistry = deps.formatters || formatters;
    for (const name of OVERRIDDEN_FORMATTERS) {
        const nativeFormat = formattersRegistry.get(name, null);
        if (!nativeFormat || nativeFormat.__isBsFormatter__) {
            continue;   // absent upstream, or already installed
        }
        const bsFormat = (value, options = {}) => {
            if (!value) {
                return nativeFormat(value, options);
            }
            // Exclusions here are by field NAME only: `getFormattedValue`
            // (views/utils.js:139-151) hands over the field descriptor but not the
            // record, so there is no model to match on. That still covers
            // create_date/write_date and the other technical names, which are what
            // actually appear as optional list columns.
            const fieldName = options.field && options.field.name;
            if (fieldName && EXCLUDED_FIELDS.has(fieldName)) {
                return nativeFormat(value, options);
            }
            const bs = toBsParts(value, name === "datetime", options);
            if (!bs) {
                // Outside the supported table. Showing the Gregorian date is far
                // better than showing nothing or a guess.
                return nativeFormat(value, options);
            }
            const text = formatBs(bs, { npDigits });
            if (name === "datetime" && options.showTime !== false) {
                // Keep the time component: only the calendar changes, not the
                // clock. Rendered from the same user-zone value the date came
                // from, so the two cannot disagree.
                return `${text} ${localTimeText(value, options)}`;
            }
            return text;
        };
        // Preserve the native descriptor's own metadata. `extractOptions` is what
        // carries `numeric` / `show_time` from the arch into the formatter
        // (formatters.js:93,107); dropping it would silently ignore those options.
        bsFormat.extractOptions = nativeFormat.extractOptions;
        bsFormat.__isBsFormatter__ = true;
        formattersRegistry.add(name, bsFormat, { force: true });
    }

    return installed;
}

/**
 * The value as the USER sees it on the wall clock.
 *
 * A Datetime is stored UTC, and core formats it with
 * `value.setZone(options.tz || "default")` (`core/l10n/dates.js:434`) -- where
 * "default" is the **browser** zone, because Odoo never assigns
 * `luxon.Settings.defaultZone` in production. Deriving a BS day from that is
 * wrong for the 5h45m before midnight in Kathmandu: 2026-09-08 18:30 UTC is
 * already the 9th there, and the 8th in UTC.
 *
 * A plain Date carries no instant, so re-zoning it would invent one and shift
 * the day for anyone west of UTC. Hence the explicit `isDatetime` flag rather
 * than sniffing the value.
 */
function localTime(value, options = {}) {
    return value.setZone(options.tz || user.tz || "default");
}

/**
 * The clock part of a datetime, in the user's own time format.
 *
 * `localization` is a **throwing Proxy** (`core/l10n/localization.js:26-40`):
 * reading a key before `localization_service` has populated it raises rather than
 * returning undefined. A formatter can be called from anywhere, so the read is
 * guarded and falls back to an unambiguous 24-hour clock. Hard-coding the format
 * outright would ignore a user who has chosen a 12-hour locale.
 */
function localTimeText(value, options = {}) {
    const local = localTime(value, options);
    let format = "HH:mm:ss";
    try {
        if (localization.timeFormat) {
            format = localization.timeFormat;
        }
    } catch {
        // Parameters not ready; the fallback above stands.
    }
    if (options.showSeconds === false) {
        format = format.replace(/[:.]ss/, "");
    }
    return local.toFormat(format);
}

function toBsParts(value, isDatetime, options = {}) {
    const local = isDatetime ? localTime(value, options) : value;
    try {
        return adToBs(local.year, local.month, local.day);
    } catch {
        return null;
    }
}

installCalendarOverrides(CALENDAR);
