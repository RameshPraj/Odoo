/** "Nepali Calendar" client action -- a browsable Bikram Sambat month grid.
 *
 * Registered as the client action tag `l10n_np_bs.calendar`, reachable from the
 * Nepali Calendar menu item. Purely a reference/lookup view: it renders BS
 * months, highlights today, and shows the Gregorian equivalent of every day.
 */
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import {
    adToBs, bsToAd, bsMonthLength, bsMonthName, bsWeekdayNames,
    toNpDigits, BS_MIN_YEAR, BS_MAX_YEAR,
} from "./bs_convert";
import { BS_MONTHS_EN } from "./bs_calendar_data";

const AD_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export class BSCalendar extends Component {
    static template = "l10n_np_bs.Calendar";
    static props = { ...standardActionServiceProps };

    setup() {
        const t = this.todayBs();
        this.state = useState({ year: t.year, month: t.month, npDigits: true });
    }

    todayAdParts() {
        const n = new Date();
        return [n.getFullYear(), n.getMonth() + 1, n.getDate()];
    }

    todayBs() {
        return adToBs(...this.todayAdParts());
    }

    num(n) {
        return this.state.npDigits ? toNpDigits(n) : String(n);
    }

    get title() {
        return `${bsMonthName(this.state.month)} ${this.num(this.state.year)}`;
    }

    /** English gloss, e.g. "Bhadra 2083 · Aug-Sep 2026" */
    get subtitle() {
        const { year, month } = this.state;
        const first = bsToAd(year, month, 1);
        const last = bsToAd(year, month, bsMonthLength(year, month));
        const a = `${AD_MONTHS[first.month - 1]} ${first.year}`;
        const b = `${AD_MONTHS[last.month - 1]} ${last.year}`;
        const span = a === b ? a : `${a} – ${b}`;
        return `${BS_MONTHS_EN[month - 1]} ${year} · ${span}`;
    }

    get todayLabel() {
        const t = this.todayBs();
        const [y, m, d] = this.todayAdParts();
        return `${bsMonthName(t.month)} ${this.num(t.day)}, ${this.num(t.year)}` +
               `  (${AD_MONTHS[m - 1]} ${d}, ${y})`;
    }

    get weekdays() {
        return bsWeekdayNames();
    }

    get cells() {
        const { year, month } = this.state;
        const len = bsMonthLength(year, month);
        const first = bsToAd(year, month, 1);
        const lead = new Date(Date.UTC(first.year, first.month - 1, first.day)).getUTCDay();
        const today = this.todayBs();
        const out = [];
        for (let i = 0; i < lead; i++) {
            out.push({ key: `b${i}`, blank: true });
        }
        for (let d = 1; d <= len; d++) {
            const ad = bsToAd(year, month, d);
            const dow = new Date(Date.UTC(ad.year, ad.month - 1, ad.day)).getUTCDay();
            out.push({
                key: `d${d}`,
                blank: false,
                label: this.num(d),
                adLabel: `${AD_MONTHS[ad.month - 1]} ${ad.day}`,
                saturday: dow === 6,            // Saturday is the weekly holiday in Nepal
                today: today.year === year && today.month === month && today.day === d,
            });
        }
        return out;
    }

    shift(delta) {
        let y = this.state.year;
        let m = this.state.month + delta;
        if (m < 1) { m = 12; y -= 1; }
        if (m > 12) { m = 1; y += 1; }
        if (y < BS_MIN_YEAR || y > BS_MAX_YEAR) {
            return;
        }
        this.state.year = y;
        this.state.month = m;
    }

    shiftYear(delta) {
        const y = this.state.year + delta;
        if (y < BS_MIN_YEAR || y > BS_MAX_YEAR) {
            return;
        }
        this.state.year = y;
    }

    goToday() {
        const t = this.todayBs();
        this.state.year = t.year;
        this.state.month = t.month;
    }

    toggleDigits() {
        this.state.npDigits = !this.state.npDigits;
    }

    get rangeHint() {
        return _t("Supported range: BS %(min)s – %(max)s", {
            min: BS_MIN_YEAR, max: BS_MAX_YEAR,
        });
    }
}

registry.category("actions").add("l10n_np_bs.calendar", BSCalendar);
