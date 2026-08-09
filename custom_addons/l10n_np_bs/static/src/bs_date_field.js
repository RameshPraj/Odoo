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
import { _t } from "@web/core/l10n/translation";
import {
    adToBs, bsToAd, bsMonthLength, bsMonthName, bsWeekdayNames,
    formatBs, parseBs, toNpDigits, BS_MIN_YEAR, BS_MAX_YEAR,
} from "./bs_convert";

export class BSDateField extends Component {
    static template = "l10n_np_bs.BSDateField";
    static props = {
        ...standardFieldProps,
        monthName: { type: Boolean, optional: true },
        npDigits: { type: Boolean, optional: true },
    };
    static defaultProps = { monthName: false, npDigits: true };

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

    // -- current value ----------------------------------------------------

    /** The record's Gregorian value as a Luxon DateTime, or null. */
    get value() {
        return this.props.record.data[this.props.name] || null;
    }

    /** The value as {year, month, day} in BS, or null if unset/out of range. */
    get bsValue() {
        const v = this.value;
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
        // Build the Luxon DateTime from the field's existing one so we keep its
        // zone behaviour, rather than constructing a raw JS Date.
        const current = this.value;
        const next = current
            ? current.set({ year: ad.year, month: ad.month, day: ad.day })
            : luxon.DateTime.local(ad.year, ad.month, ad.day);
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

    todayParts() {
        const n = new Date();
        return [n.getFullYear(), n.getMonth() + 1, n.getDate()];
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
            help: _t("Render digits in Devanagari. Enabled by default."),
        },
    ],
    extractProps: ({ options }) => ({
        monthName: Boolean(options.month_name),
        npDigits: options.np_digits === undefined ? true : Boolean(options.np_digits),
    }),
};

registry.category("fields").add("bs_date", bsDateField);
