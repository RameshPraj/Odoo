/** The "in 3 days" widget, in Bikram Sambat.
 *
 * `RemainingDaysField` renders a relative phrase and, on hover, the absolute
 * date. For a BS user that absolute date has to be BS — otherwise a due date
 * reads Gregorian in one place and Nepali everywhere else on the same screen.
 *
 * The rule worth asserting here is **not** the conversion, which
 * `bs_convert.test.js` and the exhaustive 46,022-day Python cross-check in
 * `tests/test_conversion_contract.py` already own. It is the **date-vs-datetime
 * zoning guard**, which exists nowhere else in the JavaScript:
 *
 *   A `Datetime` is a UTC instant and must be shifted into the reader's zone
 *   before a day is taken from it. A `Date` has no instant, so shifting it
 *   *invents* one and moves the day for anyone west of UTC.
 *
 * `tests/test_timezone_and_reports.py` calls this "the one that matters most" and
 * covers it on the server. This is its browser-side twin, and until now nothing
 * asserted it: `invoice_date_due` is a `Date`, so a regression that re-zoned
 * everything would move due dates by a day for a whole class of users and raise
 * nothing.
 *
 * The records here are plain objects rather than Luxon values on purpose.
 * `bsTextFor` only reads `.year/.month/.day` and optionally calls `.setZone`, so
 * a fake whose `setZone` *throws* turns "was it re-zoned?" into an assertion
 * rather than an inspection.
 */
import { describe, expect, test } from "@odoo/hoot";
import { bsTextFor } from "@nepali_calendar_core/remaining_days_patch";

describe.current.tags("headless");

/** A stand-in for a Luxon value that refuses to be re-zoned. */
function immovable(year, month, day) {
    return {
        year,
        month,
        day,
        setZone() {
            throw new Error(
                "setZone() was called on a Date; a Date has no instant, so " +
                    "re-zoning it invents one and shifts the day west of UTC"
            );
        },
    };
}

/** A stand-in that records the zone it was asked to move to. */
function movable(year, month, day, moved) {
    return {
        year,
        month,
        day,
        setZone(zone) {
            moved.push(zone);
            return { year, month, day, setZone() {} };
        },
    };
}

const record = (value, type) => ({
    data: { the_field: value },
    fields: { the_field: { type } },
});

test("a Date is never re-zoned", () => {
    // The load-bearing test in this file. If bsTextFor ever drops its type
    // check, `immovable` throws and this fails loudly instead of silently
    // shifting a due date by one day.
    const text = bsTextFor(record(immovable(2026, 9, 8), "date"), "the_field");
    expect(typeof text).toBe("string");
});

test("a Datetime is re-zoned before its day is taken", () => {
    const moved = [];
    const text = bsTextFor(record(movable(2026, 9, 8, moved), "datetime"), "the_field");
    expect(moved.length).toBe(1, {
        message: "a Datetime is a UTC instant and must be shifted before a day "
            + "is read off it",
    });
    expect(typeof text).toBe("string");
});

test("an empty value defers to Odoo", () => {
    expect(bsTextFor(record(false, "date"), "the_field")).toBe(null);
    expect(bsTextFor(record(undefined, "date"), "the_field")).toBe(null);
});

test("an excluded field defers to Odoo", () => {
    // create_date is in EXCLUDED_FIELDS: users cross-reference it against server
    // logs, which are AD. Rendering it in BS here would contradict the same
    // field rendered by the date widget, which honours the same exclusion list.
    const rec = {
        data: { create_date: immovable(2026, 9, 8) },
        fields: { create_date: { type: "datetime" } },
    };
    expect(bsTextFor(rec, "create_date")).toBe(null);
});

test("a date outside the supported table returns null rather than a guess", () => {
    // The asymmetry this module chose deliberately: showing the Gregorian date is
    // a cosmetic regression, showing a converted guess is a correctness one. Year
    // 1800 is far below the BS table's range.
    expect(bsTextFor(record(immovable(1800, 1, 1), "date"), "the_field")).toBe(null);
});

test("a supported date converts to Bikram Sambat digits", () => {
    // 2026-09-08 AD is BS 2083-05-23. Asserted loosely on the year only: the
    // exact string is bs_convert's contract, tested there and against
    // nepali-datetime on all 46,022 days in range.
    const text = bsTextFor(record(immovable(2026, 9, 8), "date"), "the_field");
    expect(text).toInclude("2083");
});
