/** Bikram Sambat <-> Gregorian conversion, browser side.
 *
 * Mirrors tools/bs.py. Both read the same generated month-length table, so a
 * date rendered here always matches what the server stores.
 *
 * All functions work on plain {year, month, day} objects and Luxon DateTime,
 * never on raw JS Date, to avoid timezone drift: a Date at midnight local time
 * can fall on the previous day in UTC, which would shift the BS date by one.
 */
import {
    BS_MIN_YEAR, BS_MAX_YEAR, BS_EPOCH_AD, BS_MONTH_DAYS,
    BS_MONTHS_NE, BS_NP_DIGITS,
    BS_WEEKDAYS_NE_SHORT, BS_WEEKDAYS_NE_LONG,
} from "./bs_calendar_data";

// From the generated table, which gets it from tools/names.py -- the same source
// the server uses. Previously declared literally here, i.e. a second copy.
const NP_DIGITS = BS_NP_DIGITS;
const MS_PER_DAY = 86400000;

export class BSRangeError extends Error {}

/** Devanagari digits for display. */
export function toNpDigits(text) {
    return String(text).replace(/\d/g, (d) => NP_DIGITS[Number(d)]);
}

/** Inverse of toNpDigits. */
export function fromNpDigits(text) {
    return String(text).replace(/[०-९]/g, (d) => String(NP_DIGITS.indexOf(d)));
}

/** Days in a given BS month (1-12). */
export function bsMonthLength(year, month) {
    if (year < BS_MIN_YEAR || year > BS_MAX_YEAR) {
        throw new BSRangeError(`BS year ${year} outside ${BS_MIN_YEAR}..${BS_MAX_YEAR}`);
    }
    // The month was unchecked (BS-11). `BS_MONTH_DAYS[y][month - 1]` is an
    // array index, so month 13 read one past the row and month 0 read index -1,
    // and JavaScript answers `undefined` to both rather than failing. That
    // `undefined` then propagated into date arithmetic as NaN, which surfaces
    // far from here as a blank or nonsense date. The year check above already
    // sets the precedent: refuse, do not guess.
    if (!Number.isInteger(month) || month < 1 || month > 12) {
        throw new BSRangeError(`BS month ${month} outside 1..12`);
    }
    return BS_MONTH_DAYS[year - BS_MIN_YEAR][month - 1];
}

/**
 * Throw unless (year, month, day) is a date that actually exists.
 *
 * Round-tripping through `Date.UTC` is the check: it normalises out-of-range
 * components, so a date survives unchanged if and only if it was real.
 */
function assertRealGregorianDate(year, month, day) {
    if (![year, month, day].every(Number.isInteger)) {
        throw new BSRangeError(`${year}-${month}-${day} is not a whole date`);
    }
    const probe = new Date(Date.UTC(year, month - 1, day));
    if (
        probe.getUTCFullYear() !== year ||
        probe.getUTCMonth() !== month - 1 ||
        probe.getUTCDate() !== day
    ) {
        throw new BSRangeError(`${year}-${month}-${day} is not a real date`);
    }
}

/** Days elapsed between two Gregorian dates, calendar-day accurate (UTC math). */
function daysBetweenUTC(y1, m1, d1, y2, m2, d2) {
    const a = Date.UTC(y1, m1 - 1, d1);
    const b = Date.UTC(y2, m2 - 1, d2);
    return Math.round((b - a) / MS_PER_DAY);
}

/**
 * Gregorian -> BS.
 * @param {number} year @param {number} month 1-12 @param {number} day
 * @returns {{year:number, month:number, day:number}}
 */
export function adToBs(year, month, day) {
    // Gregorian input is validated here (BS-12), because `Date.UTC` normalises
    // rather than rejects: `Date.UTC(2026, 8, 31)` is the 1st of October, so
    // `adToBs(2026, 9, 31)` used to return a real BS date for a day that never
    // existed. Silently converting a non-existent date is the same class of
    // fault as converting one out of range -- a plausible wrong answer -- and
    // this module's rule is that a guess is worse than a refusal.
    assertRealGregorianDate(year, month, day);
    let remaining = daysBetweenUTC(BS_EPOCH_AD[0], BS_EPOCH_AD[1], BS_EPOCH_AD[2], year, month, day);
    if (remaining < 0) {
        throw new BSRangeError(`${year}-${month}-${day} is before the supported range`);
    }
    let y = BS_MIN_YEAR;
    while (y <= BS_MAX_YEAR) {
        const total = BS_MONTH_DAYS[y - BS_MIN_YEAR].reduce((a, b) => a + b, 0);
        if (remaining < total) {
            break;
        }
        remaining -= total;
        y += 1;
    }
    if (y > BS_MAX_YEAR) {
        throw new BSRangeError(`${year}-${month}-${day} is after the supported range`);
    }
    let m = 1;
    while (m <= 12 && remaining >= BS_MONTH_DAYS[y - BS_MIN_YEAR][m - 1]) {
        remaining -= BS_MONTH_DAYS[y - BS_MIN_YEAR][m - 1];
        m += 1;
    }
    return { year: y, month: m, day: remaining + 1 };
}

/**
 * BS -> Gregorian.
 * @returns {{year:number, month:number, day:number}}
 */
export function bsToAd(year, month, day) {
    year = Number(year);
    month = Number(month);
    day = Number(day);
    if (!(month >= 1 && month <= 12)) {
        throw new BSRangeError(`BS month ${month} out of range`);
    }
    const len = bsMonthLength(year, month);
    if (!(day >= 1 && day <= len)) {
        throw new BSRangeError(`BS ${year}-${month} has ${len} days, got day ${day}`);
    }
    let days = 0;
    for (let y = BS_MIN_YEAR; y < year; y++) {
        days += BS_MONTH_DAYS[y - BS_MIN_YEAR].reduce((a, b) => a + b, 0);
    }
    for (let m = 1; m < month; m++) {
        days += BS_MONTH_DAYS[year - BS_MIN_YEAR][m - 1];
    }
    days += day - 1;
    const t = Date.UTC(BS_EPOCH_AD[0], BS_EPOCH_AD[1] - 1, BS_EPOCH_AD[2]) + days * MS_PER_DAY;
    const dt = new Date(t);
    return { year: dt.getUTCFullYear(), month: dt.getUTCMonth() + 1, day: dt.getUTCDate() };
}

/** Weekday index (0=Sunday) of a BS date. */
export function bsWeekday(year, month, day) {
    const ad = bsToAd(year, month, day);
    return new Date(Date.UTC(ad.year, ad.month - 1, ad.day)).getUTCDay();
}

export function bsMonthName(month) {
    return BS_MONTHS_NE[month - 1];
}

/**
 * Weekday names, Sunday first.
 * @param {boolean} long the long form (आइतबार) rather than the short (आइत)
 */
export function bsWeekdayNames({ long = false } = {}) {
    return long ? BS_WEEKDAYS_NE_LONG : BS_WEEKDAYS_NE_SHORT;
}

/**
 * Format a BS triple.
 * @param {object} bs {year, month, day}
 * @param {object} opts {monthName:boolean, npDigits:boolean}
 */
// npDigits defaults to FALSE, matching tools/bs.py's `np_digits=False`. The two
// sides previously disagreed, so the same date rendered differently depending on
// which layer produced it. Devanagari is opt-in via the company setting.
export function formatBs(bs, { monthName = false, npDigits = false } = {}) {
    if (!bs) {
        return "";
    }
    const pad = (n) => String(n).padStart(2, "0");
    // The day is zero-padded in BOTH forms, matching tools/bs.py's `%02d`. The two
    // sides disagreed here (`2083 भदौ 9` in the browser, `2083 भदौ 09` on a PDF of
    // the same record), and padding is the form that lines up in a list column.
    const out = monthName
        ? `${bs.year} ${bsMonthName(bs.month)} ${pad(bs.day)}`
        : `${bs.year}-${pad(bs.month)}-${pad(bs.day)}`;
    return npDigits ? toNpDigits(out) : out;
}

/** Parse "2083-05-24" / "२०८३-०५-२४" / "2083/5/24" -> {year, month, day}. */
export function parseBs(text) {
    const parts = fromNpDigits(String(text).trim()).split(/[-/.\s]+/).filter(Boolean);
    if (parts.length !== 3 || parts.some((p) => !/^\d+$/.test(p))) {
        return null;
    }
    const [y, m, d] = parts.map(Number);
    try {
        bsToAd(y, m, d);          // validates
        return { year: y, month: m, day: d };
    } catch {
        return null;
    }
}

export { BS_MIN_YEAR, BS_MAX_YEAR };
