# -*- coding: utf-8 -*-
"""The calendar preference: resolution, plumbing, and what it must never touch.

The preference is the whole coverage mechanism -- every date field follows it --
so its edge cases matter more than any single widget. Five things are asserted:

  TestPreferenceResolution  user -> company -> 'ad', including the case where a
                            user is BS inside a company that is not
  TestPreferencePlumbing    the resolved value reaches env.context, and a change
                            takes effect without a server restart
  TestSelfService           a plain user can set their own calendar and cannot
                            set anyone else's
  TestStorageInvariance     **the important one.** A BS user and an AD user
                            writing the same date must produce byte-identical
                            PostgreSQL columns. If this fails, the module has
                            corrupted the ledger and every other test is noise.
  TestSessionInfo           over real HTTP: the browser is actually handed the
                            preference (`session_info` reads `request.session`,
                            so this cannot be asserted in a transaction)
"""
import datetime

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, tagged

from ..models.res_users import CONTEXT_KEY


class CalendarFixtures:
    """One company, three users: BS, AD, and one with no preference of their own.

    A mixin rather than a base class because the `session_info` assertions need
    `HttpCase` (there is no `request` in a plain transaction) while everything
    else only needs `TransactionCase`, and paying for a browser fixture in every
    test would be wasteful.
    """

    #: Logins double as passwords so `authenticate()` can be called with them.
    def _setup_calendar_users(self):
        self.company = self.env["res.company"].create({"name": "BS Test Co"})
        Users = self.env["res.users"].with_context(no_reset_password=True)

        def _user(login, calendar_system):
            return Users.create({
                "name": login,
                "login": login,
                "password": login,
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
                "calendar_system": calendar_system,
                # Odoo 19 renamed this from `groups_id`.
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            })

        self.user_bs = _user("bs_user@example.com", "bs")
        self.user_ad = _user("ad_user@example.com", "ad")
        self.user_unset = _user("unset_user@example.com", False)


@tagged("-at_install", "post_install")
class CalendarCase(CalendarFixtures, TransactionCase):

    def setUp(self):
        super().setUp()
        self._setup_calendar_users()

    def _env_for(self, user):
        """An environment shaped like a real request's.

        `self.env(user=X)` inherits the *parent's* context; it does not call
        `context_get()`. A real RPC does, which is how `calendar_system` gets into
        the context at all -- so a test that skips it is not testing the same code
        path the server runs.
        """
        context = self.env["res.users"].with_user(user).context_get()
        return self.env(user=user, context=dict(context))


class TestPreferenceResolution(CalendarCase):

    def test_user_preference_wins(self):
        self.company.calendar_system = "ad"
        self.assertEqual(
            self.env["res.users"]._resolve_calendar_system(self.user_bs), "bs",
            "an explicit user preference must beat the company default"
        )

    def test_user_can_opt_out_of_a_bs_company(self):
        """The case that makes this a preference rather than a company switch.

        A Nepali company defaults to BS; its expat controller sets AD. If the
        company default won, that user could not opt out.
        """
        self.company.calendar_system = "bs"
        self.assertEqual(
            self.env["res.users"]._resolve_calendar_system(self.user_ad), "ad"
        )

    def test_company_default_applies_when_user_is_unset(self):
        self.company.calendar_system = "bs"
        self.assertEqual(
            self.env["res.users"]._resolve_calendar_system(self.user_unset), "bs"
        )

    def test_the_company_default_can_never_be_null(self):
        """`required=True` is enforced in PostgreSQL, not just in the UI.

        This is the stronger of the two guarantees and worth pinning: it means the
        resolver's third level is defence in depth rather than a case that occurs.
        Dropping `required` would make a NULL company default representable and
        change what the next test is defending against.
        """
        self.env.cr.execute("""
            SELECT is_nullable FROM information_schema.columns
             WHERE table_name = 'res_company' AND column_name = 'calendar_system'
        """)
        self.assertEqual(
            self.env.cr.fetchone()[0], "NO",
            "res_company.calendar_system lost its NOT NULL constraint; the "
            "AD fallback is now reachable from the database and this test's "
            "sibling should be rewritten to exercise it via SQL"
        )

    def test_falls_back_to_ad_when_neither_is_set(self):
        """AD is the fallback, so installing the module changes nothing by itself.

        A module that silently flipped every date in an existing database on
        install would be indefensible.

        Exercised on **in-memory** records. The company column is NOT NULL (see
        the test above), so this state cannot be reached by writing -- an earlier
        version of this test tried raw SQL and was correctly rejected by the
        constraint. `new()` builds unsaved records, which runs the resolver's real
        code path with both levels falsy and never touches the database.
        """
        company = self.env["res.company"].new({"calendar_system": False})
        user = self.env["res.users"].new({
            "calendar_system": False,
            "company_id": company.id,
        })
        self.assertFalse(user.calendar_system)
        self.assertFalse(user.company_id.calendar_system)
        self.assertEqual(
            self.env["res.users"]._resolve_calendar_system(user), "ad"
        )

    def test_company_default_is_ad_out_of_the_box(self):
        fresh = self.env["res.company"].create({"name": "Fresh Co"})
        self.assertEqual(fresh.calendar_system, "ad")

    def test_resolution_does_not_require_company_read_access(self):
        """A plain user must be able to resolve their own calendar.

        The helper sudo()s for exactly this reason; without it, resolution raises
        for any user who cannot read res.company, which is most of them.
        """
        as_user = self.env["res.users"].with_user(self.user_unset)
        self.company.sudo().calendar_system = "bs"
        self.assertEqual(as_user._resolve_calendar_system(), "bs")


class TestPreferencePlumbing(CalendarCase):

    def test_context_carries_the_resolved_value(self):
        env = self.env(user=self.user_bs)
        self.assertEqual(env["res.users"].context_get().get(CONTEXT_KEY), "bs")

        env_ad = self.env(user=self.user_ad)
        self.assertEqual(env_ad["res.users"].context_get().get(CONTEXT_KEY), "ad")

    def test_context_get_still_carries_core_keys(self):
        """Adding a key must not displace lang or tz.

        `context_get` rebuilds a frozendict; dropping a core key would break
        translation and timezone handling everywhere.
        """
        context = self.env(user=self.user_bs)["res.users"].context_get()
        self.assertIn("lang", context)
        self.assertIn("tz", context)

    def test_change_takes_effect_without_a_restart(self):
        """`context_get` is ormcache'd on uid.

        Without `calendar_system` in `_get_invalidation_fields`, the write below
        succeeds and the user keeps seeing the old calendar until the server
        restarts -- a silent failure, which is the worst kind.
        """
        env = self.env(user=self.user_unset)
        self.company.calendar_system = "ad"
        self.assertEqual(env["res.users"].context_get().get(CONTEXT_KEY), "ad")

        self.user_unset.calendar_system = "bs"
        self.assertEqual(
            env["res.users"].context_get().get(CONTEXT_KEY), "bs",
            "the preference change did not invalidate the context cache; check "
            "_get_invalidation_fields()"
        )

    def test_invalidation_fields_is_a_superset_of_core(self):
        """Return a union, not a replacement.

        `_get_invalidation_fields` returns a set; returning only our own field
        would stop `lang`, `tz` and group changes from invalidating anything.
        """
        fields_set = self.env["res.users"]._get_invalidation_fields()
        self.assertIn("calendar_system", fields_set)
        for core_field in ("lang", "tz", "group_ids", "company_id"):
            self.assertIn(core_field, fields_set)


class TestSelfService(CalendarCase):

    def test_a_plain_user_can_set_their_own_calendar(self):
        """Otherwise the preference is admin-only, which defeats the point."""
        own = self.env["res.users"].with_user(self.user_unset).browse(self.user_unset.id)
        own.write({"calendar_system": "bs"})
        self.assertEqual(self.user_unset.calendar_system, "bs")

    def test_a_plain_user_cannot_set_someone_elses(self):
        """SELF_WRITEABLE_FIELDS must not become a general write grant."""
        other = self.env["res.users"].with_user(self.user_unset).browse(self.user_ad.id)
        with self.assertRaises(AccessError):
            other.write({"calendar_system": "bs"})

    def test_the_field_is_readable_by_its_owner(self):
        """Without SELF_READABLE_FIELDS the Preferences form cannot render it."""
        own = self.env["res.users"].with_user(self.user_bs).browse(self.user_bs.id)
        self.assertEqual(own.read(["calendar_system"])[0]["calendar_system"], "bs")

    def test_the_override_preserves_the_core_self_field_lists(self):
        """These are properties returning lists; concatenate, never replace."""
        users = self.env["res.users"]
        for name in ("tz", "lang", "email"):
            self.assertIn(name, users.SELF_READABLE_FIELDS)
        self.assertIn("calendar_system", users.SELF_READABLE_FIELDS)
        self.assertIn("tz", users.SELF_WRITEABLE_FIELDS)
        self.assertIn("calendar_system", users.SELF_WRITEABLE_FIELDS)


class TestStorageInvariance(CalendarCase):
    """Gregorian storage is untouched. The single most important guarantee here.

    Everything else in this module is presentation. If a BS user's writes land in
    PostgreSQL differently from an AD user's, the module has corrupted the data
    and no amount of correct rendering compensates.
    """

    #: `res.currency.rate.name` is a plain stored `fields.Date` reachable with
    #: only this module's dependencies (`base`), which `res.partner` is not --
    #: partner has no stored date column at all. `group_user` has read-only
    #: access, so writes go through `sudo()`; that elevates rights while keeping
    #: the user and context, so the BS calendar context is still active for the
    #: write, which is what these tests are about.
    VALUE = datetime.date(2026, 9, 9)

    def _create_rate(self, user, currency_xmlid="base.EUR"):
        """One rate, written while `user`'s calendar context is active.

        `currency_xmlid` varies because `res_currency_rate_unique_name_per_day`
        forbids two rates for the same currency, company and date -- so the
        two-users-one-date comparison needs two currencies.
        """
        env = self._env_for(user)
        self.assertEqual(
            env.context.get(CONTEXT_KEY),
            env["res.users"]._resolve_calendar_system(user),
            "fixture is not exercising the user's calendar context"
        )
        return env["res.currency.rate"].sudo().create({
            "name": self.VALUE,
            "currency_id": env.ref(currency_xmlid).id,
            "company_id": self.company.id,
        })

    def test_the_same_date_is_stored_identically_for_both_calendars(self):
        bs_rate = self._create_rate(self.user_bs, "base.EUR")
        ad_rate = self._create_rate(self.user_ad, "base.CHF")

        self.assertEqual(bs_rate.name, ad_rate.name)
        self.assertEqual(bs_rate.name, self.VALUE)

    def test_raw_sql_column_is_gregorian_for_a_bs_user(self):
        """Read past the ORM.

        An ORM-level assertion would still pass if a converter were rewriting
        values symmetrically on read and write. Only raw SQL proves what is on
        disk.
        """
        rate = self._create_rate(self.user_bs)
        self.env.flush_all()

        self.env.cr.execute(
            "SELECT name FROM res_currency_rate WHERE id = %s", (rate.id,)
        )
        stored = self.env.cr.fetchone()[0]
        self.assertEqual(
            stored, self.VALUE,
            f"a BS user's write stored {stored!r} instead of the Gregorian "
            f"{self.VALUE!r}; storage must never be converted"
        )
        # A BS year is ~57 years ahead, so assert the year outright rather than
        # trusting the equality above to be read carefully.
        self.assertEqual(stored.year, 2026)

    def test_a_domain_search_still_uses_gregorian_bounds(self):
        """Domains are data, not presentation, and must not be reinterpreted.

        If the preference leaked into domain handling, a BS user's saved filters
        and every automated action would silently select the wrong rows.
        """
        rate = self._create_rate(self.user_bs)
        Rate = self._env_for(self.user_bs)["res.currency.rate"].sudo()

        self.assertEqual(
            Rate.search([
                ("id", "=", rate.id),
                ("name", ">=", "2026-09-01"),
                ("name", "<=", "2026-09-30"),
            ]),
            rate,
            "Gregorian domain bounds stopped matching"
        )

        # The BS equivalent (2083-05-*) must NOT match -- no reinterpretation.
        self.assertFalse(Rate.search([
            ("id", "=", rate.id),
            ("name", ">=", "2083-05-01"),
            ("name", "<=", "2083-05-30"),
        ]))

    def test_export_stays_gregorian(self):
        """`convert_to_export` feeds xlsx and CSV, which must round-trip.

        Formatting BS here would make an export non-reimportable, and the export
        path shares `convert_to_display_name` with other callers, so overriding
        either would corrupt more than the export.
        """
        rate = self._create_rate(self.user_bs)
        exported = rate.export_data(["name"])["datas"]
        # Odoo 19 hands back a `datetime.date`, not a formatted string; the
        # spreadsheet writer formats it. Either way the assertion that matters is
        # that it is the Gregorian value and not a BS string.
        self.assertEqual(exported, [[self.VALUE]])
        self.assertNotIsInstance(
            exported[0][0], str,
            "a date arriving as a string here would mean something formatted it; "
            "check that convert_to_export / convert_to_display_name are untouched"
        )


@tagged("-at_install", "post_install")
class TestSessionInfo(CalendarFixtures, HttpCase):
    """The preference must actually reach the browser.

    `session_info` is the per-user channel, and it reads `request.session`, so
    there is no `request` in a plain transaction -- these assertions need a real
    HTTP round trip. Doing it over the wire also checks the thing that matters:
    what the web client is handed, not what a Python method returns.

    The translation-hash route was considered and rejected for this: it is
    ormcache'd on `(modules, lang)` with **no uid** and served with
    `Cache-Control: public`, so a per-user value placed there would be served to
    whoever asked next.
    """

    def setUp(self):
        super().setUp()
        self._setup_calendar_users()

    def _session_info_as(self, user):
        self.authenticate(user.login, user.login)
        return self.make_jsonrpc_request("/web/session/get_session_info", {})

    def test_a_bs_user_receives_bs(self):
        info = self._session_info_as(self.user_bs)
        self.assertEqual(info.get("calendar_system"), "bs")
        self.assertIn(
            "bs_digits", info,
            "the digit style must travel with the calendar; without it the client "
            "cannot render Devanagari and silently falls back to ASCII"
        )

    def test_an_ad_user_receives_ad(self):
        info = self._session_info_as(self.user_ad)
        self.assertEqual(info.get("calendar_system"), "ad")

    def test_an_unset_user_receives_the_company_default(self):
        self.company.calendar_system = "bs"
        self.env.flush_all()
        info = self._session_info_as(self.user_unset)
        self.assertEqual(info.get("calendar_system"), "bs")

    def test_core_session_keys_survive(self):
        """Adding keys must not disturb what the client already depends on."""
        info = self._session_info_as(self.user_bs)
        for key in ("uid", "user_context", "db"):
            self.assertIn(key, info)
