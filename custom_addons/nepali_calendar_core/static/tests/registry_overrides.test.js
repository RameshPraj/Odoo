/** The dispatcher: does a date field actually render Bikram Sambat?
 *
 * This is the mechanism the entire coverage model rests on. Everything else in
 * the module is correct conversion; this is what decides whether any of it
 * reaches a user. Until this file existed, nothing asserted that a BS user gets
 * `BSDateField` on a business date, or that `create_date` stays Gregorian.
 *
 * Two properties are tested, and they pull in opposite directions:
 *
 *   1. **Coverage is global.** No per-model registration, no field list. A field
 *      nobody thought about must still follow the preference.
 *   2. **Exclusions hold.** Audit columns and technical timestamps must render
 *      Gregorian even for a BS user, because they are cross-referenced against
 *      server logs, which are AD.
 *
 * The module-load override is keyed on `session.calendar_system`, which a test
 * cannot change after import. So the override was refactored into an exported,
 * idempotent `installCalendarOverrides(calendar)` and these tests call it
 * directly. Odoo's test framework restores every registry after each test, so
 * that exercises the real production path and leaks into nothing.
 */
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { queryFirst } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    serverState,
} from "@web/../tests/web_test_helpers";

import { registry } from "@web/core/registry";

import { isExcluded } from "@nepali_calendar_core/exclusions";
import { installCalendarOverrides } from "@nepali_calendar_core/registry_overrides";

describe.current.tags("desktop");

class Ledger extends models.Model {
    _name = "ledger";

    name = fields.Char();
    /** A business date: must follow the preference. */
    entry_date = fields.Date({ string: "Entry Date" });
    /** A business datetime: the 94-field category. */
    posted_at = fields.Datetime({ string: "Posted At" });
    /** The audit pair: must stay Gregorian. */
    create_date = fields.Datetime({ string: "Created On" });

    _records = [
        {
            id: 1,
            name: "opening",
            entry_date: "2026-09-09",
            // 18:30 UTC -- already the next day in Kathmandu.
            posted_at: "2026-09-08 18:30:00",
            create_date: "2026-09-09 06:00:00",
        },
    ];
}

defineModels([Ledger]);

const BS_9TH = "2083-05-24";
const BS_8TH = "2083-05-23";

beforeEach(() => {
    onRpc("has_group", () => true);
});

/**
 * Everything the user can actually read, as one string.
 *
 * Both widgets render an editable value into `<input value="...">`, which is NOT
 * part of `textContent` -- an earlier version of these tests read `textContent`
 * and so compared against the empty string. The negative assertions passed
 * vacuously, which is worse than failing. `textContent` is still included for the
 * readonly render path, which uses a `<span>`.
 */
function visibleText() {
    const values = [...document.querySelectorAll("input")].map((el) => el.value);
    const root = queryFirst(".o_form_view") || queryFirst(".o_list_view");
    return [...values, root ? root.textContent : ""].join(" ");
}

describe("exclusion predicate", () => {
    // The predicate is the whole coverage policy, so it is worth testing on its
    // own -- independently of whether a widget renders.

    test("the audit pair is excluded on every model", () => {
        for (const model of ["account.move", "res.partner", "ledger", "anything"]) {
            expect(isExcluded(model, "create_date")).toBe(true);
            expect(isExcluded(model, "write_date")).toBe(true);
        }
    });

    test("ordinary business dates are not excluded", () => {
        // The default must be "covered". If this inverts, the module silently
        // reverts to the 20-field allowlist it was built to replace.
        for (const [model, field] of [
            ["account.move", "invoice_date"],
            ["account.move", "date"],
            ["sale.order", "commitment_date"],
            ["ledger", "entry_date"],
            ["some.model.nobody.thought.about", "deadline"],
        ]) {
            expect(isExcluded(model, field)).toBe(false, {
                message: `${model}.${field} should follow the preference`,
            });
        }
    });

    test("technical models are excluded by prefix", () => {
        expect(isExcluded("ir.cron", "nextcall")).toBe(true);
        expect(isExcluded("ir.cron.trigger", "call_at")).toBe(true);
        expect(isExcluded("bus.presence", "last_poll")).toBe(true);
        expect(isExcluded("ir.logging", "create_date")).toBe(true);
    });

    test("a model is not excluded merely for sharing a prefix with words", () => {
        // "ir.attachment" is excluded; "ir.attachmentless" would be a false
        // positive of prefix matching. Documented as accepted: no such model
        // exists, and the alternative is an exact-match list that must be
        // maintained per model.
        expect(isExcluded("ir.attachment", "create_date")).toBe(true);
        expect(isExcluded("account.move", "invoice_date")).toBe(false);
    });

    test("a specific pair can be excluded without excluding its model", () => {
        // mail.activity.date_deadline is a real user-facing due date, so
        // `mail.*` cannot be excluded wholesale.
        expect(isExcluded("mail.message", "date")).toBe(true);
        expect(isExcluded("mail.activity", "date_deadline")).toBe(false);
    });

    test("a null model does not throw", () => {
        // Some render paths have no resModel; the predicate must degrade to a
        // field-name check rather than crash the view.
        expect(isExcluded(undefined, "create_date")).toBe(true);
        expect(isExcluded(null, "entry_date")).toBe(false);
    });
});

describe("AD is the default", () => {
    // The registry swap happens at module load, keyed on `session.calendar_system`,
    // which hoot leaves unset -- so a mounted view here is an AD user's view. That
    // makes this the AD half of the contract, and it is the half that matters most
    // for safety: proof that installing the module changes nothing for a user who
    // has not opted in, which is what allows it onto an existing database at all.

    test("an AD user sees no Bikram Sambat anywhere", async () => {
        await mountView({
            type: "form",
            resModel: "ledger",
            resId: 1,
            arch: `
                <form>
                    <field name="entry_date"/>
                    <field name="create_date"/>
                </form>`,
        });
        await animationFrame();

        const shown = visibleText();
        // Positive assertion FIRST, so the negatives below cannot pass over an
        // empty string. Without this the test proves nothing.
        expect(shown).toInclude("2026", {
            message: "no Gregorian date was rendered at all, so the negative "
                + "assertions below would pass vacuously",
        });
        expect(shown).not.toInclude(BS_9TH, {
            message: "a user who has not chosen BS must see no BS dates at all",
        });
        expect(shown).not.toInclude(BS_8TH);
    });

    test("a list of dates still mounts", async () => {
        // Guards against the override breaking the widget it wraps: a dispatcher
        // that throws would take down every list containing a date, which is most
        // of them.
        await mountView({
            type: "list",
            resModel: "ledger",
            arch: `
                <list>
                    <field name="entry_date"/>
                    <field name="posted_at"/>
                </list>`,
        });
        await animationFrame();
        expect(".o_data_row").toHaveCount(1);
    });
});

describe("BS rendering, through the widget", () => {
    // The BS half. Reached via an explicit `widget="bs_date"` rather than by
    // faking a session, because `widget=` registers unconditionally and therefore
    // renders the same component the dispatcher selects. This tests the rendering
    // and the timezone handling; what it does not test is the *selection* -- see
    // the note at the end of the file.

    test("a date field renders Bikram Sambat", async () => {
        await mountView({
            type: "form",
            resModel: "ledger",
            resId: 1,
            arch: `<form><field name="entry_date" widget="bs_date"/></form>`,
        });
        await animationFrame();
        expect(".o_field_bs_date_input").toHaveValue(BS_9TH);
    });

    test("a datetime is shifted into the user's timezone first", async () => {
        // THE case. `posted_at` is 2026-09-08 18:30 UTC, which is 00:15 on the
        // 9th in Kathmandu. Deriving the BS day from the UTC instant gives
        // 2083-05-23 -- wrong for the 5h45m before local midnight, i.e. every
        // evening.
        serverState.timezone = "Asia/Kathmandu";
        await mountView({
            type: "form",
            resModel: "ledger",
            resId: 1,
            arch: `<form><field name="posted_at" widget="bs_date"/></form>`,
        });
        await animationFrame();

        expect(".o_field_bs_date_input").toHaveValue(BS_9TH, {
            message: "18:30 UTC is the 9th in Kathmandu; showing the 8th means the "
                + "UTC instant was converted without shifting to user.tz",
        });
    });

    test("the same instant is the previous day for a UTC user", async () => {
        // Not a bug being tolerated: 18:30 UTC really is the 8th in UTC. Asserted
        // so that a "fix" which hard-codes Kathmandu is caught.
        serverState.timezone = "UTC";
        await mountView({
            type: "form",
            resModel: "ledger",
            resId: 1,
            arch: `<form><field name="posted_at" widget="bs_date"/></form>`,
        });
        await animationFrame();

        expect(".o_field_bs_date_input").toHaveValue(BS_8TH);
    });

    test("a plain date is not shifted by the timezone", async () => {
        // The mirror-image bug: applying an offset to a value with no instant
        // would make an invoice dated the 9th print as the 8th west of UTC.
        for (const tz of ["Asia/Kathmandu", "UTC", "America/New_York"]) {
            serverState.timezone = tz;
            await mountView({
                type: "form",
                resModel: "ledger",
                resId: 1,
                arch: `<form><field name="entry_date" widget="bs_date"/></form>`,
            });
            await animationFrame();
            expect(".o_field_bs_date_input").toHaveValue(BS_9TH, {
                message: `a date field shifted in ${tz}`,
            });
        }
    });
});

describe("selection -- the composition", () => {
    // The test that was previously impossible, and the reason
    // `installCalendarOverrides` is exported.
    //
    // Odoo's test framework snapshots every registry before each test and
    // restores it after (`env_test_helpers.js`), so calling the real installer
    // against the real `fields` registry is safe here and leaks into nothing.
    // That means these tests exercise the actual production code path rather than
    // a re-implementation of it.

    test("a business date picks the BS widget, an audit column does not", async () => {
        expect(installCalendarOverrides("bs")).toEqual(["date", "datetime", "daterange"]);

        await mountView({
            type: "form",
            resModel: "ledger",
            resId: 1,
            arch: `
                <form>
                    <field name="entry_date"/>
                    <field name="create_date"/>
                </form>`,
        });
        await animationFrame();

        // No `widget=` anywhere in that arch: the choice is entirely the
        // dispatcher's, which is the point.
        expect(".o_field_widget[name=entry_date] .o_field_bs_date_input").toHaveCount(1, {
            message: "a business date must render Bikram Sambat for a BS user",
        });
        expect(".o_field_widget[name=create_date] .o_field_bs_date_input").toHaveCount(0, {
            message: "create_date is on the exclusion list and must stay Gregorian; "
                + "users cross-reference it against server logs, which are AD",
        });
        expect(visibleText()).toInclude(BS_9TH);
    });

    test("a datetime business field also follows the preference", async () => {
        // 94 of the 237 business date fields are datetimes, so this is not an
        // afterthought -- it is 40% of the surface.
        serverState.timezone = "Asia/Kathmandu";
        installCalendarOverrides("bs");

        await mountView({
            type: "form",
            resModel: "ledger",
            resId: 1,
            arch: `<form><field name="posted_at"/></form>`,
        });
        await animationFrame();

        expect(".o_field_widget[name=posted_at] .o_field_bs_date_input").toHaveCount(1);
        // And still timezone-correct through the dispatcher, not just through an
        // explicit widget=.
        expect(".o_field_bs_date_input").toHaveValue(BS_9TH);
    });

    test("an AD user gets Odoo's own widgets untouched", () => {
        const before = registry.category("fields").get("date");
        expect(installCalendarOverrides("ad")).toEqual([]);
        expect(registry.category("fields").get("date")).toBe(before, {
            message: "installing with calendar='ad' must be a complete no-op, so an "
                + "AD user's client is identical to one without this module",
        });
    });

    test("installing twice does not wrap the wrapper", async () => {
        // Without the guard this recurses forever at render time: the wrapper's
        // native fallback would be the wrapper itself.
        installCalendarOverrides("bs");
        installCalendarOverrides("bs");

        await mountView({
            type: "form",
            resModel: "ledger",
            resId: 1,
            arch: `<form><field name="create_date"/></form>`,
        });
        await animationFrame();

        // create_date is excluded, so it renders through the NATIVE fallback --
        // exactly the path double-installation would have broken.
        expect(".o_field_widget[name=create_date]").toHaveCount(1);
        expect(".o_field_widget[name=create_date] .o_field_bs_date_input").toHaveCount(0);
        expect(visibleText()).toInclude("2026");
    });

    test("the native extractProps is preserved", async () => {
        // Options already written into existing views must keep working; the
        // wrapper spreads the native descriptor's extracted props rather than
        // replacing them. `required` is the cheapest observable one.
        installCalendarOverrides("bs");

        await mountView({
            type: "form",
            resModel: "ledger",
            resId: 1,
            arch: `<form><field name="entry_date" required="1"/></form>`,
        });
        await animationFrame();
        expect(".o_field_widget[name=entry_date]").toHaveClass("o_required_modifier");
    });

    test("the parser accepts Bikram Sambat and still accepts Gregorian", () => {
        installCalendarOverrides("bs");
        const parse = registry.category("parsers").get("date");

        // BS in.
        const fromBs = parse("2083-05-24");
        expect(fromBs.year).toBe(2026);
        expect(fromBs.month).toBe(9);
        expect(fromBs.day).toBe(9);

        // Gregorian must still work: a BS user typing an AD date, or any saved
        // filter and automated action already in the database, must not break.
        expect(() => parse("09/09/2026")).not.toThrow();
    });

    test("the parser override is not applied twice", () => {
        installCalendarOverrides("bs");
        const once = registry.category("parsers").get("date");
        installCalendarOverrides("bs");
        expect(registry.category("parsers").get("date")).toBe(once, {
            message: "a doubly-wrapped parser still works but each call pays for "
                + "two failed BS parses; the guard keeps it at one",
        });
    });
});
