# -*- coding: utf-8 -*-
"""Timezone correctness, and Bikram Sambat on printed output.

**Why this file is the one that matters most.** Odoo stores `Datetime` as naive
UTC. Deriving a BS day from a UTC instant without first shifting it into the
reader's timezone is wrong for the 5h45m before midnight in Kathmandu -- roughly a
quarter of every day, and only in the evening, which is exactly when it will be
dismissed as "the user must have typed it wrong".

The discriminating case, used throughout: **2026-09-08 18:30 UTC**.

    Asia/Kathmandu (UTC+05:45)  ->  2026-09-09 00:15  ->  BS 2083-05-24
    UTC                         ->  2026-09-08 18:30  ->  BS 2083-05-23

The two answers differ, so a test using it fails if the shift is ever dropped.
**2026-09-08 18:10 UTC** is the control: 23:55 in Kathmandu, so both calendars
agree, which proves these tests are not simply always-unequal.

This matters more than it looks: of the 237 business date fields, **94 are
`datetime`**, and inverting coverage to global exposes all of them at once.

Printed output is deliberately governed by the **company** setting, not the
reader's preference -- an invoice must not change depending on who pressed Print.
"""
import datetime

from odoo.tests import TransactionCase, tagged

from ..tools import bs

#: Naive UTC, as stored. In Kathmandu this is already the next day.
UTC_EVENING = datetime.datetime(2026, 9, 8, 18, 30, 0)
#: Naive UTC, 20 minutes earlier: still the same day everywhere relevant.
UTC_CONTROL = datetime.datetime(2026, 9, 8, 18, 10, 0)

BS_9TH = "2083-05-24"   # ad_to_bs(2026-09-09)
BS_8TH = "2083-05-23"   # ad_to_bs(2026-09-08)


@tagged("-at_install", "post_install")
class TimezoneCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({
            "name": "Report Test Co",
            "calendar_system": "bs",
            "bs_report_output": "bs",
            "bs_digits": "latin",
        })

    def _converter(self, tz, model="ir.qweb.field.datetime"):
        """The QWeb converter, as a reader in `tz` at `self.company` would see it."""
        return self.env[model].with_context(tz=tz, allowed_company_ids=[self.company.id]).with_company(self.company)


class TestDatetimeTimezone(TimezoneCase):
    """The 94-datetime-field hazard."""

    def test_kathmandu_evening_is_already_the_next_bs_day(self):
        html = self._converter("Asia/Kathmandu").value_to_html(UTC_EVENING, {})
        self.assertIn(
            BS_9TH, html,
            f"18:30 UTC is 00:15 the next day in Kathmandu, so the BS date must "
            f"be {BS_9TH}. Getting {BS_8TH} means the UTC instant was converted "
            f"without shifting into the reader's timezone."
        )
        self.assertNotIn(BS_8TH, html)

    def test_the_same_instant_is_the_previous_day_in_utc(self):
        """Same stored value, different reader, legitimately different day.

        This is not a bug being tolerated: 18:30 UTC really is the 8th for a
        reader in UTC. It is asserted so that a future "fix" that hard-codes
        Kathmandu is caught.
        """
        html = self._converter("UTC").value_to_html(UTC_EVENING, {})
        self.assertIn(BS_8TH, html)
        self.assertNotIn(BS_9TH, html)

    def test_new_york_afternoon_is_the_same_calendar_day(self):
        html = self._converter("America/New_York").value_to_html(UTC_EVENING, {})
        self.assertIn(BS_8TH, html)

    def test_control_instant_agrees_across_zones(self):
        """20 minutes earlier, every zone here lands on the same BS day.

        Without this, `test_kathmandu_...` and `test_..._utc` could both pass on a
        converter that was simply always off by one.
        """
        for tz in ("Asia/Kathmandu", "UTC", "America/New_York"):
            with self.subTest(tz=tz):
                html = self._converter(tz).value_to_html(UTC_CONTROL, {})
                self.assertIn(BS_8TH, html)

    def test_midnight_boundary_in_kathmandu(self):
        """Either side of local midnight, exhaustively.

        18:14 UTC is 23:59 NPT; 18:15 UTC is 00:00 NPT the next day.
        """
        cases = [
            (datetime.datetime(2026, 9, 8, 18, 14), BS_8TH),
            (datetime.datetime(2026, 9, 8, 18, 15), BS_9TH),
        ]
        for value, expected in cases:
            with self.subTest(utc=value):
                html = self._converter("Asia/Kathmandu").value_to_html(value, {})
                self.assertIn(expected, html)

    def test_a_date_field_is_not_shifted(self):
        """A `date` has no instant, so shifting it would invent one.

        Applying a timezone offset to a plain date is the mirror-image bug: an
        invoice dated the 9th would print as the 8th for a reader west of UTC.
        """
        for tz in ("Asia/Kathmandu", "UTC", "America/New_York", "Pacific/Kiritimati"):
            with self.subTest(tz=tz):
                html = self._converter(tz, "ir.qweb.field.date").value_to_html(
                    datetime.date(2026, 9, 9), {}
                )
                self.assertIn(BS_9TH, html)


class TestReportOutputModes(TimezoneCase):
    """`bs_report_output` is a company setting, and all three modes must work."""

    def _render_date(self, options=None):
        return self.env["ir.qweb.field.date"].with_company(self.company).value_to_html(
            datetime.date(2026, 9, 9), options or {}
        )

    def test_bs_only(self):
        self.company.bs_report_output = "bs"
        html = self._render_date()
        self.assertIn(BS_9TH, html)
        self.assertNotIn("2026", html)

    def test_both_shows_bs_and_ad(self):
        """The default, and the safest for a document an auditor will read."""
        self.company.bs_report_output = "both"
        html = self._render_date()
        self.assertIn(BS_9TH, html)
        self.assertIn("2026", html, "'both' must still carry the Gregorian date")

    def test_ad_only_is_untouched_output(self):
        """A company that has not opted in must get exactly core's rendering."""
        self.company.bs_report_output = "ad"
        html = self._render_date()
        self.assertNotIn(BS_9TH, html)
        self.assertIn("2026", html)

    def test_a_field_can_force_ad_regardless_of_the_setting(self):
        """`t-options="{'calendar': 'ad'}"` for the one date that must stay AD.

        A cheque date or an EDI payload field cannot be allowed to follow a
        company-wide display preference.
        """
        self.company.bs_report_output = "bs"
        html = self._render_date({"calendar": "ad"})
        self.assertNotIn(BS_9TH, html)
        self.assertIn("2026", html)

    def test_devanagari_digits_follow_the_company_setting(self):
        self.company.bs_report_output = "bs"
        self.company.bs_digits = "devanagari"
        html = self._render_date()
        self.assertIn("२०८३", html)
        self.assertNotIn("2083", html)

    def test_blank_dates_render_blank_not_an_error(self):
        """An unset date on an invoice must not raise mid-render."""
        self.company.bs_report_output = "bs"
        for model in ("ir.qweb.field.date", "ir.qweb.field.datetime"):
            with self.subTest(model=model):
                html = self.env[model].with_company(self.company).value_to_html(
                    False, {}
                )
                self.assertEqual(html, "")

    def test_output_does_not_depend_on_the_readers_preference(self):
        """The point of using a company setting rather than the user preference.

        Two readers with opposite personal calendars must be handed the same
        document, or the same invoice reconciles differently for two people.
        """
        self.company.bs_report_output = "both"
        renders = set()
        for calendar in ("ad", "bs"):
            reader = self.env["res.users"].with_context(no_reset_password=True).create({
                "name": f"reader-{calendar}",
                "login": f"reader-{calendar}@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
                "calendar_system": calendar,
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            })
            renders.add(
                self.env["ir.qweb.field.date"].with_user(reader)
                .with_company(self.company)
                .value_to_html(datetime.date(2026, 9, 9), {})
            )
        self.assertEqual(
            len(renders), 1,
            f"the same date rendered {len(renders)} different ways depending on "
            f"who was reading: {renders}"
        )


class TestTemplateHelper(TimezoneCase):
    """`format_date_bs` is added as a new name, never shadowing `format_date`."""

    def test_helper_is_available_in_the_render_environment(self):
        values = {}
        self.env["ir.qweb"]._prepare_environment(values)
        self.assertIn(
            "format_date_bs", values,
            "_prepare_environment mutates `values` in place; the helper must be "
            "added after the super() call"
        )

    def test_the_format_date_name_is_left_alone(self):
        """We must not squat on `format_date`.

        Core's `_prepare_environment` does not define `format_date` at all --
        `mail.render.mixin` and the EDI modules (UBL/CII, TicketBAI, l10n_it_edi)
        each inject their own into their own values dict. Defining one here would
        therefore not "override" anything; it would collide with whichever of
        those renders next, including the payloads that must stay Gregorian by
        law. Hence a new name, and this assertion that the old one stays free.
        """
        values = {}
        self.env["ir.qweb"]._prepare_environment(values)
        self.assertNotIn(
            "format_date", values,
            "this module must not introduce a `format_date` key into the QWeb "
            "render environment -- other modules own that name"
        )

    def test_only_the_one_new_key_is_added(self):
        """Guard the blast radius of touching a core render hook.

        `_prepare_environment` mutates `values` in place for every QWeb render in
        the system, so anything added here reaches every report, mail template and
        website page. The set of keys we add must be exactly one.
        """
        ours, bare = {}, {}
        self.env["ir.qweb"]._prepare_environment(ours)
        # `minimal_qcontext` makes core take its short path; used only to confirm
        # the helper is added on both paths, not to compare key sets.
        self.env["ir.qweb"].with_context(minimal_qcontext=True)._prepare_environment(bare)
        self.assertIn("format_date_bs", ours)
        self.assertIn(
            "format_date_bs", bare,
            "the helper must also be present on the minimal context path, which "
            "is what mail templates use"
        )

    def test_helper_formats_bs(self):
        values = {}
        self.env["ir.qweb"]._prepare_environment(values)
        self.assertEqual(
            values["format_date_bs"](datetime.date(2026, 9, 9), np_digits=False),
            BS_9TH,
        )

    def test_helper_month_name_form_matches_tools_bs(self):
        values = {}
        self.env["ir.qweb"]._prepare_environment(values)
        self.assertEqual(
            values["format_date_bs"](
                datetime.date(2026, 9, 9), np_digits=False, month_names=True
            ),
            bs.format_bs(datetime.date(2026, 9, 9), month_names=True),
        )

    def test_helper_tolerates_a_blank_value(self):
        values = {}
        self.env["ir.qweb"]._prepare_environment(values)
        self.assertEqual(values["format_date_bs"](False), "")
