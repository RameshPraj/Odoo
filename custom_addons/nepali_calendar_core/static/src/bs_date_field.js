/** `bs_date` field widget -- shows and edits a Date field in Bikram Sambat.
 *
 *     <field name="birthday" widget="bs_date"/>
 *
 * The record value stays a normal Gregorian date; only the rendering and the
 * typed input are BS. Options:
 *     monthName  show "२०८३ भदौ २४" instead of "२०८३-०५-२४"
 *     npDigits   Devanagari digits (default true)
 */
import { Component, useState, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";
import {
    adToBs, bsToAd, bsMonthLength, bsMonthName, bsWeekdayNames,
    formatBs, parseBs, toNpDigits, BS_MIN_YEAR, BS_MAX_YEAR,
} from "./bs_convert";

export class BSDateField extends Component {
    static template = "nepali_calendar_core.BSDateField";
    static props = {
        ...standardFieldProps,
        monthName: { type: Boolean, optional: true },
        npDigits: { type: Boolean, optional: true },
    };
    // Latin digits by default, matching tools/bs.py's `np_digits=False`. The two
    // sides used to disagree, so the same date printed differently depending on
    // which layer produced it.
    static defaultProps = { monthName: false, npDigits: false };

    setup() {
        this.notification = useService("notification");
        this.inputRef = useRef("input");
        this.state = useState({
            open: false,
            // the BS year/month currently shown in the picker grid
            viewYear: null,
            viewMonth: null,
            error: false,
        });
    }

    // -- timezone ---------------------------------------------------------

    /** True when this field carries a time, and therefore a timezone. */
    get isDatetime() {
        return this.props.record.fields[this.props.name].type === "datetime";
    }

    /**
     * The value as the *user* sees it on the wall clock.
     *
     * A Datetime is stored UTC and deserialised by core with
     * `.setZone("default")`, which resolves to the **browser** zone -- Odoo never
     * assigns `luxon.Settings.defaultZone` in production. For a calendar widget
     * that is wrong: a value at 19:00 UTC is the 9th in Kathmandu (UTC+05:45) and
     * the 8th in UTC, so the BS day flipped depending on the viewer's laptop.
     *
     * Re-zoning to `user.tz` makes the day the user's own day. A plain Date needs
     * no shift -- it has no instant, so shifting it would invent one.
     */
    get localValue() {
        const v = this.props.record.data[this.props.name] || null;
        if (!v || !this.isDatetime || !user.tz) {
            return v;
        }
        return v.setZone(user.tz);
    }

    // -- current value ----------------------------------------------------

    /** The record's Gregorian value as a Luxon DateTime, or null. */
    get value() {
        return this.props.record.data[this.props.name] || null;
    }

    /** The value as {year, month, day} in BS, or null if unset/out of range. */
    get bsValue() {
        const v = this.localValue;
        if (!v) {
            return null;
        }
        try {
            return adToBs(v.year, v.month, v.day);
        } catch {
            return null;
        }
    }

    get displayText() {
        const bs = this.bsValue;
        if (!bs) {
            return this.value ? _t("out of BS range") : "";
        }
        return formatBs(bs, { monthName: this.props.monthName, npDigits: this.props.npDigits });
    }

    get isOutOfRange() {
        return Boolean(this.value) && !this.bsValue;
    }

    // -- writing back ------------------------------------------------------

    async setFromBs(y, m, d) {
        let ad;
        try {
            ad = bsToAd(y, m, d);
        } catch (e) {
            this.notification.add(e.message, { type: "warning" });
            return;
        }
        const parts = { year: ad.year, month: ad.month, day: ad.day };
        let next;
        if (this.isDatetime) {
            // Set the calendar fields in the USER's zone, then hand back a value
            // in the zone core expects. Setting them on a browser-zoned DateTime
            // would store an instant that is a different day in Kathmandu -- the
            // mirror image of the read-side bug.
            const base = this.localValue || luxon.DateTime.now().setZone(user.tz || "default");
            next = base.set(parts);
        } else {
            // A plain Date carries no instant; `.set` on the existing value keeps
            // core's own zone handling intact.
            next = this.value
                ? this.value.set(parts)
                : luxon.DateTime.local(ad.year, ad.month, ad.day);
        }
        await this.props.record.update({ [this.props.name]: next });
    }

    async onInputChange(ev) {
        const raw = ev.target.value.trim();
        if (!raw) {
            this.state.error = false;
            await this.props.record.update({ [this.props.name]: false });
            return;
        }
        const bs = parseBs(raw);
        if (!bs) {
            this.state.error = true;
            this.notification.add(
                _t("Enter a Bikram Sambat date as YYYY-MM-DD, e.g. 2083-05-24 (BS %(min)s-%(max)s).",
                   { min: BS_MIN_YEAR, max: BS_MAX_YEAR }),
                { type: "warning" }
            );
            return;
        }
        this.state.error = false;
        await this.setFromBs(bs.year, bs.month, bs.day);
    }

    // -- picker -----------------------------------------------------------

    togglePicker() {
        if (this.props.readonly) {
            return;
        }
        if (!this.state.open) {
            const bs = this.bsValue || adToBs(...this.todayParts());
            this.state.viewYear = bs.year;
            this.state.viewMonth = bs.month;
        }
        this.state.open = !this.state.open;
    }

    /**
     * Today, in the user's timezone.
     *
     * Previously `new Date()` -- the raw browser clock. For a Nepali accountant on
     * a laptop set to UTC, that made the widget's highlighted "today" a day behind
     * Nepal between 18:15 and midnight UTC, and disagree with the server's
     * `fields.Date.context_today`, which uses `res.users.tz`.
     */
    todayParts() {
        const now = luxon.DateTime.now().setZone(user.tz || "default");
        return [now.year, now.month, now.day];
    }

    shiftMonth(delta) {
        let y = this.state.viewYear;
        let m = this.state.viewMonth + delta;
        if (m < 1) {
            m = 12;
            y -= 1;
        } else if (m > 12) {
            m = 1;
            y += 1;
        }
        if (y < BS_MIN_YEAR || y > BS_MAX_YEAR) {
            return;
        }
        this.state.viewYear = y;
        this.state.viewMonth = m;
    }

    get headerLabel() {
        const label = `${bsMonthName(this.state.viewMonth)} ${this.state.viewYear}`;
        return this.props.npDigits ? toNpDigits(label) : label;
    }

    get weekdayLabels() {
        return bsWeekdayNames();
    }

    /** Grid cells: leading blanks for alignment, then day numbers. */
    get monthCells() {
        const { viewYear: y, viewMonth: m } = this.state;
        if (!y) {
            return [];
        }
        const len = bsMonthLength(y, m);
        const firstAd = bsToAd(y, m, 1);
        const lead = new Date(Date.UTC(firstAd.year, firstAd.month - 1, firstAd.day)).getUTCDay();
        const sel = this.bsValue;
        const today = adToBs(...this.todayParts());
        const cells = [];
        for (let i = 0; i < lead; i++) {
            cells.push({ blank: true, key: `b${i}` });
        }
        for (let d = 1; d <= len; d++) {
            cells.push({
                key: `d${d}`,
                day: d,
                label: this.props.npDigits ? toNpDigits(d) : String(d),
                selected: Boolean(sel && sel.year === y && sel.month === m && sel.day === d),
                today: today.year === y && today.month === m && today.day === d,
            });
        }
        return cells;
    }

    async pick(day) {
        await this.setFromBs(this.state.viewYear, this.state.viewMonth, day);
        this.state.open = false;
    }

    async clear() {
        await this.props.record.update({ [this.props.name]: false });
        this.state.open = false;
    }

    async pickToday() {
        const t = adToBs(...this.todayParts());
        await this.setFromBs(t.year, t.month, t.day);
        this.state.open = false;
    }
}

export const bsDateField = {
    component: BSDateField,
    displayName: _t("Bikram Sambat Date"),
    supportedTypes: ["date", "datetime"],
    supportedOptions: [
        {
            label: _t("Month name"),
            name: "month_name",
            type: "boolean",
            help: _t("Show '२०८३ भदौ २४' instead of '२०८३-०५-२४'."),
        },
        {
            label: _t("Nepali digits"),
            name: "np_digits",
            type: "boolean",
            help: _t(
                "Render digits in Devanagari. Defaults to the company's Bikram Sambat numerals setting."
            ),
        },
    ],
    extractProps: ({ options }) => ({
        monthName: Boolean(options.month_name),
        // Falls back to the COMPANY setting, not to a hard-coded `true`. It was
        // `true` here while `defaultProps`, `formatBs` and `tools/bs.py` all
        // defaulted to Latin, so an explicit `widget="bs_date"` rendered
        // Devanagari and every other route rendered ASCII -- the same date in two
        // scripts on one screen. An explicit option still wins.
        npDigits: options.np_digits === undefined
            ? session.bs_digits === "devanagari"
            : Boolean(options.np_digits),
    }),
};

registry.category("fields").add("bs_date", bsDateField);
