/** The browser half of the conversion contract.
 *
 * `tests/test_conversion_contract.py` asserts the Python half properly, but can
 * only check the JS half by grepping its source -- there is no JS runtime in a
 * Python test. That is not a test, it is a reminder. These are the real ones.
 *
 * The cases below are deliberately the SAME dates the Python suite uses, so the
 * two files are cross-checking one contract rather than testing two things that
 * happen to both pass.
 */
import { describe, expect, test } from "@odoo/hoot";

import {
    adToBs,
    bsMonthLength,
    bsMonthName,
    bsToAd,
    bsWeekday,
    bsWeekdayNames,
    BSRangeError,
    formatBs,
    fromNpDigits,
    parseBs,
    toNpDigits,
    BS_MIN_YEAR,
    BS_MAX_YEAR,
} from "@nepali_calendar_core/bs_convert";

describe.current.tags("headless");

/** [AD y, m, d], [BS y, m, d] -- shared with the Python suite. */
const KNOWN = [
    [[2026, 9, 9], [2083, 5, 24]],
    [[2026, 4, 14], [2083, 1, 1]],   // Nepali new year
    [[2000, 1, 1], [2056, 9, 17]],
];

describe("adToBs / bsToAd", () => {
    test("known dates convert both ways", () => {
        for (const [[ay, am, ad_], [by, bm, bd]] of KNOWN) {
            expect(adToBs(ay, am, ad_)).toEqual({ year: by, month: bm, day: bd });
            expect(bsToAd(by, bm, bd)).toEqual({ year: ay, month: am, day: ad_ });
        }
    });

    test("round trips over a long stride", () => {
        // Every 97 days for ~50 years: hits every month and both leap patterns
        // without walking all 46,000 days in a browser.
        let t = Date.UTC(1990, 0, 1);
        const end = Date.UTC(2040, 0, 1);
        while (t < end) {
            const d = new Date(t);
            const bs = adToBs(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
            const back = bsToAd(bs.year, bs.month, bs.day);
            expect(back).toEqual({
                year: d.getUTCFullYear(),
                month: d.getUTCMonth() + 1,
                day: d.getUTCDate(),
            });
            t += 97 * 86400000;
        }
    });

    test("the first and last supported days convert", () => {
        const first = bsToAd(BS_MIN_YEAR, 1, 1);
        expect(adToBs(first.year, first.month, first.day)).toEqual({
            year: BS_MIN_YEAR, month: 1, day: 1,
        });

        const lastDay = bsMonthLength(BS_MAX_YEAR, 12);
        const last = bsToAd(BS_MAX_YEAR, 12, lastDay);
        expect(adToBs(last.year, last.month, last.day)).toEqual({
            year: BS_MAX_YEAR, month: 12, day: lastDay,
        });
    });

    test("out of range throws rather than guessing", () => {
        // The month-length table IS the algorithm; there is no formula to
        // extrapolate, so a guess outside it would be silently wrong.
        expect(() => adToBs(1850, 1, 1)).toThrow(BSRangeError);
        expect(() => bsMonthLength(BS_MAX_YEAR + 1, 1)).toThrow(BSRangeError);
        expect(() => bsToAd(BS_MIN_YEAR - 1, 1, 1)).toThrow(BSRangeError);
    });

    test("an impossible day in a real month throws", () => {
        // BS months run 29-32 days with no rule, so this cannot be range-checked
        // arithmetically -- only against the table.
        const len = bsMonthLength(2083, 5);
        expect(() => bsToAd(2083, 5, len + 1)).toThrow(BSRangeError);
        expect(() => bsToAd(2083, 13, 1)).toThrow(BSRangeError);
    });

    test("conversion is unaffected by the browser timezone", () => {
        // The functions take plain numbers and do UTC arithmetic internally,
        // precisely so a laptop's clock cannot shift a stored date by a day.
        const before = adToBs(2026, 9, 9);
        const original = luxon.Settings.defaultZone;
        try {
            luxon.Settings.defaultZone = "Pacific/Kiritimati";  // UTC+14
            expect(adToBs(2026, 9, 9)).toEqual(before);
            luxon.Settings.defaultZone = "Pacific/Niue";        // UTC-11
            expect(adToBs(2026, 9, 9)).toEqual(before);
        } finally {
            luxon.Settings.defaultZone = original;
        }
    });
});

describe("formatBs", () => {
    test("numeric form is zero-padded", () => {
        expect(formatBs({ year: 2083, month: 5, day: 24 })).toBe("2083-05-24");
        expect(formatBs({ year: 2083, month: 1, day: 1 })).toBe("2083-01-01");
    });

    test("Devanagari is opt-in, not the default", () => {
        // The two layers used to disagree here: Python defaulted to ASCII and JS
        // to Devanagari, so the same date rendered in different scripts depending
        // on which one produced it.
        expect(formatBs({ year: 2083, month: 5, day: 24 })).toBe("2083-05-24");
        expect(formatBs({ year: 2083, month: 5, day: 24 }, { npDigits: true }))
            .toBe("२०८३-०५-२४");
    });

    test("month-name form is space separated with a padded day", () => {
        // Matches tools/bs.py's `f"{y:04d} {MONTHS_NE[m]} {d:02d}"`. JS previously
        // left the day unpadded, so a PDF and a list view disagreed.
        expect(formatBs({ year: 2083, month: 5, day: 24 }, { monthName: true }))
            .toBe("2083 भदौ 24");
        expect(formatBs({ year: 2083, month: 1, day: 1 }, { monthName: true }))
            .toBe("2083 बैशाख 01");
    });

    test("a missing value is empty, not a crash", () => {
        expect(formatBs(null)).toBe("");
        expect(formatBs(undefined)).toBe("");
    });
});

describe("parseBs", () => {
    test("accepts every separator the Python side accepts", () => {
        const expected = { year: 2083, month: 5, day: 24 };
        for (const text of [
            "2083-05-24",
            "2083/05/24",
            "2083.05.24",
            "2083 05 24",
            "2083-5-24",
            "  2083-05-24  ",
            "२०८३-०५-२४",
            "२०८३/०५/२४",
        ]) {
            expect(parseBs(text)).toEqual(expected, {
                message: `parseBs rejected ${JSON.stringify(text)}`,
            });
        }
    });

    test("returns null rather than throwing", () => {
        // The deliberate asymmetry with Python, which raises: the widget must not
        // break the form while a user is still typing.
        for (const bad of ["", "not a date", "2083-13-01", "2083-05", "abc-de-fg"]) {
            expect(parseBs(bad)).toBe(null, {
                message: `parseBs(${JSON.stringify(bad)}) should be null`,
            });
        }
    });

    test("round trips with formatBs", () => {
        for (const text of ["2083-05-24", "2056-09-17", "1975-01-01"]) {
            const bs = parseBs(text);
            expect(formatBs(bs)).toBe(text);
        }
    });
});

describe("digits", () => {
    test("round trip", () => {
        expect(toNpDigits("2083-05-24")).toBe("२०८३-०५-२४");
        expect(fromNpDigits("२०८३-०५-२४")).toBe("2083-05-24");
        expect(fromNpDigits(toNpDigits("1975"))).toBe("1975");
    });

    test("non-digits pass through untouched", () => {
        expect(toNpDigits("2083 भदौ 24")).toBe("२०८३ भदौ २४");
    });
});

describe("names and weekdays", () => {
    test("month names are 1-based", () => {
        expect(bsMonthName(1)).toBe("बैशाख");
        expect(bsMonthName(5)).toBe("भदौ");
        expect(bsMonthName(12)).toBe("चैत");
    });

    test("weekdays come in both lengths", () => {
        // Python carried only the long form and JS only the short, so neither
        // could render what the other did.
        expect(bsWeekdayNames()).toHaveLength(7);
        expect(bsWeekdayNames()[0]).toBe("आइत");
        expect(bsWeekdayNames({ long: true })[0]).toBe("आइतबार");
    });

    test("weeks start on Sunday", () => {
        // AD 2026-09-09 (BS 2083-05-24) is a Wednesday -> Sunday-first index 3.
        expect(bsWeekday(2083, 5, 24)).toBe(3);
        // AD 2026-09-13 is a Sunday.
        expect(bsWeekday(2083, 5, 28)).toBe(0);
    });
});

describe("month lengths", () => {
    test("every month in a sample of years is 29..32 days", () => {
        // A value outside this band means the table was parsed wrongly, which a
        // spot-check of individual dates can miss.
        for (const year of [1975, 2000, 2050, 2083, 2100]) {
            let total = 0;
            for (let month = 1; month <= 12; month++) {
                const len = bsMonthLength(year, month);
                expect(len).toBeGreaterThan(28);
                expect(len).toBeLessThan(33);
                total += len;
            }
            // A BS year tracks the solar year, so it must be 365 or 366 days.
            expect(total).toBeGreaterThan(364);
            expect(total).toBeLessThan(367);
        }
    });
});

describe("refusing input that is not a date", () => {
    // Both of these returned a plausible answer for an impossible input, which
    // is the worst outcome for a converter: a wrong date nobody questions.
    // Refusing is not a regression -- showing a guess is.

    test("a month outside 1..12 is refused, not read past the row", () => {
        // BS-11. `BS_MONTH_DAYS[y][month - 1]` is an array index, so month 13
        // read one past the row and month 0 read index -1; JavaScript answers
        // `undefined` to both, which becomes NaN downstream.
        for (const month of [0, 13, 99, -1]) {
            expect(() => bsMonthLength(2083, month)).toThrow(BSRangeError);
        }
        expect(() => bsMonthLength(2083, 1.5)).toThrow(BSRangeError);
    });

    test("a Gregorian date that never existed is refused", () => {
        // BS-12. `Date.UTC(2026, 8, 31)` is the 1st of October, so this used to
        // convert the 31st of September into a real BS date.
        expect(() => adToBs(2026, 9, 31)).toThrow(BSRangeError);
        expect(() => adToBs(2026, 2, 30)).toThrow(BSRangeError);
        expect(() => adToBs(2025, 2, 29)).toThrow(BSRangeError);  // not a leap year
        expect(() => adToBs(2026, 13, 1)).toThrow(BSRangeError);
        expect(() => adToBs(2026, 0, 1)).toThrow(BSRangeError);
    });

    test("the 29th of February is accepted in a leap year", () => {
        // The control for the rule above: the check must reject impossible
        // dates without rejecting awkward real ones.
        expect(() => adToBs(2024, 2, 29)).not.toThrow();
    });

    test("valid input still converts", () => {
        // The control that matters most. Every rejection test above would also
        // pass against a function that threw unconditionally.
        expect(bsMonthLength(2083, 5)).toBeGreaterThan(28);
        const bs = adToBs(2026, 9, 9);
        expect(bs.year).toBe(2083);
        expect(bs.month).toBe(5);
        expect(bs.day).toBe(24);
    });
});
