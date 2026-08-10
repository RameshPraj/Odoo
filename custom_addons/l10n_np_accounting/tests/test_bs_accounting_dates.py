# -*- coding: utf-8 -*-
"""Tests for the "Bikram Sambat accounting dates" setting.

The risky part is not injecting the widget, it is the arch cache. Odoo caches
the processed arch per model/view; if the cache key does not include the setting,
the first user to open a form decides what every other user sees. So there is a
test for exactly that.
"""
from lxml import etree

from odoo.tests import TransactionCase, tagged

GROUP = "l10n_np_accounting.group_bs_accounting_dates"


@tagged("-at_install", "post_install")
class TestBsAccountingDates(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env.ref(GROUP)
        cls.accountant = cls.env.ref("account.group_account_user")

        # The setting grants the group through `base.group_user.implied_ids`, so
        # while it is switched on in this database *every* internal user holds
        # it. Drop that implication inside the test transaction so these tests
        # control the group per user and pass whether or not the live database
        # has the setting enabled.
        cls.env.ref("base.group_user").implied_ids = [(3, cls.group.id)]

        cls.bs_user = cls.env["res.users"].create({
            "name": "Nepali Accountant", "login": "np_bs_on",
            "group_ids": [(6, 0, [cls.accountant.id, cls.group.id])],
        })
        cls.ad_user = cls.env["res.users"].create({
            "name": "Gregorian Controller", "login": "np_bs_off",
            "group_ids": [(6, 0, [cls.accountant.id])],
        })
        cls.ad_user.group_ids = [(3, cls.group.id)]

    def setUp(self):
        super().setUp()
        # Guard the precondition rather than silently asserting the wrong thing.
        if self.ad_user.has_group(GROUP):
            self.skipTest("could not produce a user without the BS date group")

    def _widgets(self, user, model, field, view_type="form", view_ref=None):
        """The widget attribute on every node for `field`, as `user` sees it."""
        records = self.env[model].with_user(user)
        arch, _view = records._get_view(
            view_id=self.env.ref(view_ref).id if view_ref else None,
            view_type=view_type)
        return [node.get("widget")
                for node in arch.iter("field") if node.get("name") == field]

    # ---- the setting does what it says -------------------------------------

    def test_accounting_date_is_bs_when_enabled(self):
        widgets = self._widgets(self.bs_user, "account.move", "date",
                               view_ref="account.view_move_form")
        self.assertTrue(widgets, "the Accounting Date field is not in the move form")
        self.assertTrue(all(w == "bs_date" for w in widgets),
                        f"expected every 'date' node to be bs_date, got {widgets}")

    def test_accounting_date_is_gregorian_when_disabled(self):
        widgets = self._widgets(self.ad_user, "account.move", "date",
                               view_ref="account.view_move_form")
        self.assertTrue(widgets)
        self.assertTrue(all(w != "bs_date" for w in widgets),
                        f"expected no bs_date without the group, got {widgets}")

    def test_every_occurrence_is_patched_not_just_the_first(self):
        """account.view_move_form carries two invoice_date nodes, customer and
        vendor. Name-based view inheritance would patch only the first; this is
        the reason the arch is walked instead."""
        widgets = self._widgets(self.bs_user, "account.move", "invoice_date",
                               view_ref="account.view_move_form")
        self.assertGreater(len(widgets), 1,
                           "expected more than one invoice_date node in this view")
        self.assertTrue(all(w == "bs_date" for w in widgets),
                        f"an occurrence was missed: {widgets}")

    def test_journal_items_list_is_patched(self):
        widgets = self._widgets(self.bs_user, "account.move.line", "date",
                               view_type="list",
                               view_ref="account.view_move_line_tree")
        self.assertTrue(widgets)
        self.assertTrue(all(w == "bs_date" for w in widgets))

    def test_our_own_wizards_are_patched(self):
        for model, field, view_ref in [
            ("account.lock.dates", "hard_lock_date",
             "l10n_np_accounting.view_account_lock_dates_form"),
            ("account.financial.statements.wizard", "date_to",
             "account_financial_statements.view_financial_statements_wizard_form"),
        ]:
            widgets = self._widgets(self.bs_user, model, field, view_ref=view_ref)
            self.assertTrue(widgets, f"{model}.{field} not found in {view_ref}")
            self.assertTrue(all(w == "bs_date" for w in widgets),
                            f"{model}.{field}: {widgets}")

    # ---- the parts that could go quietly wrong -----------------------------

    def test_arch_cache_does_not_leak_between_users(self):
        """Whoever opens the form first must not decide what the other sees."""
        # Warm the cache as the Gregorian user, then read as the BS user.
        first = self._widgets(self.ad_user, "account.move", "date",
                              view_ref="account.view_move_form")
        second = self._widgets(self.bs_user, "account.move", "date",
                               view_ref="account.view_move_form")
        self.assertNotIn("bs_date", first)
        self.assertIn("bs_date", second,
                      "the BS user was served the Gregorian user's cached arch")

        # And in the other order.
        third = self._widgets(self.bs_user, "account.move", "invoice_date_due",
                              view_ref="account.view_move_form")
        fourth = self._widgets(self.ad_user, "account.move", "invoice_date_due",
                               view_ref="account.view_move_form")
        self.assertIn("bs_date", third)
        self.assertNotIn("bs_date", fourth,
                         "the Gregorian user was served the BS user's cached arch")

    def test_an_explicit_widget_is_never_overridden(self):
        """A view that deliberately asks for another widget must keep it."""
        view = self.env["ir.ui.view"].create({
            "name": "bs test: explicit widget wins",
            "model": "account.move",
            "inherit_id": self.env.ref("account.view_move_form").id,
            "arch": """
                <field name="invoice_date_due" position="attributes">
                    <attribute name="widget">remaining_days</attribute>
                </field>
            """,
        })
        self.addCleanup(view.unlink)
        widgets = self._widgets(self.bs_user, "account.move", "invoice_date_due",
                               view_ref="account.view_move_form")
        self.assertIn("remaining_days", widgets,
                      f"an explicit widget was overwritten: {widgets}")

    def test_search_views_are_left_alone(self):
        """A widget on a search field does nothing; patching it would only
        obscure the arch."""
        arch, _view = self.env["account.move"].with_user(self.bs_user)._get_view(
            view_type="search")
        widgets = [node.get("widget") for node in arch.iter("field")]
        self.assertNotIn("bs_date", widgets)

    def test_the_setting_toggles_the_group(self):
        settings = self.env["res.config.settings"].create({})
        settings.group_l10n_np_bs_accounting_dates = True
        settings.execute()
        self.assertIn(self.group, self.env.ref("base.group_user").implied_ids,
                      "ticking the setting did not grant the group")

        settings = self.env["res.config.settings"].create({})
        settings.group_l10n_np_bs_accounting_dates = False
        settings.execute()
        self.assertNotIn(self.group, self.env.ref("base.group_user").implied_ids,
                         "unticking the setting did not revoke the group")

    # ---- digit style --------------------------------------------------------

    # Writes to res.company are flushed through cr.precommit and can outlive
    # cr.rollback(), so these use a company created for the test rather than the
    # real one.
    def _options(self, field, digits, view_ref="account.view_move_form",
                 model="account.move"):
        company = self.env["res.company"].create(
            {"name": f"BS Digits Test Co {digits}", "l10n_np_bs_digits": digits})
        # with_company() refuses a company the user is not allowed into.
        self.bs_user.company_ids = [(4, company.id)]
        records = self.env[model].with_user(self.bs_user).with_company(company)
        arch, _view = records._get_view(
            view_id=self.env.ref(view_ref).id, view_type="form")
        return [node.get("options") for node in arch.iter("field")
                if node.get("name") == field and node.get("widget") == "bs_date"]

    def test_digit_style_defaults_to_latin(self):
        """Devanagari numerals are a large change to an existing ledger, so they
        are opt-in rather than the default."""
        company = self.env["res.company"].create({"name": "BS Digits Default Co"})
        self.assertEqual(company.l10n_np_bs_digits, "latin")

    def test_latin_digits_reach_the_widget(self):
        options = self._options("date", "latin")
        self.assertTrue(options)
        self.assertTrue(all("'np_digits': false" in o for o in options), options)

    def test_devanagari_digits_reach_the_widget(self):
        options = self._options("date", "devanagari")
        self.assertTrue(options)
        self.assertTrue(all("'np_digits': true" in o for o in options), options)

    def test_digit_style_is_in_the_arch_cache_key(self):
        """Changing the style must take effect immediately, not after a restart.
        Without the company style in the cache key, whichever company rendered
        first would fix the digits for every other company."""
        latin = self._options("invoice_date", "latin")
        devanagari = self._options("invoice_date", "devanagari")
        self.assertTrue(latin and devanagari)
        self.assertNotEqual(latin, devanagari,
                            "the arch was served from cache after the style changed")

    def test_settings_field_writes_through_to_the_company(self):
        company = self.env["res.company"].create({"name": "BS Digits Settings Co"})
        self.env.user.company_ids = [(4, company.id)]
        settings = self.env["res.config.settings"].with_company(company).create(
            {"l10n_np_bs_digits": "devanagari"})
        settings.execute()
        self.assertEqual(company.l10n_np_bs_digits, "devanagari")

    def test_stored_dates_are_untouched(self):
        """The whole design rests on this: BS is presentation only."""
        journal = self.env["account.journal"].search([("type", "=", "general")], limit=1)
        if not journal:
            self.skipTest("no general journal")
        move = self.env["account.move"].with_user(self.bs_user).create({
            "move_type": "entry", "date": "2026-08-10", "journal_id": journal.id,
        })
        self.assertEqual(str(move.date), "2026-08-10")
        self.env.cr.execute("SELECT date FROM account_move WHERE id = %s", (move.id,))
        self.assertEqual(str(self.env.cr.fetchone()[0]), "2026-08-10",
                         "the stored column must stay Gregorian")

    def test_arch_stays_valid_xml(self):
        arch, _view = self.env["account.move"].with_user(self.bs_user)._get_view(
            view_id=self.env.ref("account.view_move_form").id, view_type="form")
        etree.fromstring(etree.tostring(arch))  # must not raise
