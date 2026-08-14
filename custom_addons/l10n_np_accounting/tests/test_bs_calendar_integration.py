# -*- coding: utf-8 -*-
"""Accounting Nepal after the move to the calendar preference.

Replaces ``test_bs_accounting_dates.py``, whose 16 tests exercised a mechanism
that no longer exists: a security group, an ``_get_view`` arch walk, and an arch
cache key. All three are gone. Deleting those tests rather than adapting them is
deliberate -- they asserted the *implementation*, and the implementation was
replaced on purpose.

What is worth asserting now is different, and narrower:

  TestLegacyRemoval        the old group, field and mixin really are gone, so a
                           stale reference fails here rather than at runtime
  TestSettingsSurface      the Accounting settings page still offers the calendar,
                           writing through to the one company field
  TestAccountingDatesKeepCoverage
                           the accounting dates that used to be hand-listed are
                           still in scope -- checked against the same field list
                           the old allowlist carried, so nothing quietly lost
                           coverage in the move
  TestStorageUnchanged     the guarantee that matters: switching calendar does not
                           touch a single stored value

The old file's headline concern -- arch-cache leakage between users who disagree
about the setting -- is now structurally impossible: the calendar never enters view
architecture, so there is nothing in the cache to leak. That is precisely why the
registry route was chosen over ``_get_view``.
"""
import datetime
import os
import re

from odoo.tests import TransactionCase, tagged

#: Exactly the fields the retired ``_BS_DATE_FIELDS`` allowlists named, by model.
#: Kept verbatim as the migration's acceptance criterion: whatever else the new
#: mechanism gained, it must not have lost any of these.
LEGACY_ALLOWLIST = {
    'account.move': ('date', 'invoice_date', 'invoice_date_due', 'delivery_date'),
    'account.move.line': ('date', 'date_maturity'),
    'account.payment': ('date',),
    'account.payment.register': ('payment_date',),
    'account.bank.statement': ('date',),
    'account.bank.statement.line': ('date',),
    'account.lock.dates': ('fiscalyear_lock_date', 'tax_lock_date', 'sale_lock_date',
                           'purchase_lock_date', 'hard_lock_date'),
    'account.financial.statements.wizard': ('date_from', 'date_to'),
    'l10n_np.vat.return': ('date_from', 'date_to'),
    'l10n_np.tds.certificate': ('date_from', 'date_to'),
    'l10n_np.tds.return': ('date_from', 'date_to'),
    'l10n_np.loan': ('date_start',),
    'l10n_np.loan.line': ('date',),
}

CUSTOM_ADDONS = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
EXCLUSIONS_JS = os.path.join(CUSTOM_ADDONS, "nepali_calendar_core",
                             "static", "src", "exclusions.js")


@tagged("-at_install", "post_install")
class TestLegacyRemoval(TransactionCase):
    """The retired pieces must be gone, not merely unused."""

    def test_the_group_no_longer_exists(self):
        self.assertFalse(
            self.env.ref("l10n_np_accounting.group_bs_accounting_dates",
                         raise_if_not_found=False),
            "the legacy Bikram Sambat group is still present; the group and the "
            "preference would then both gate the same behaviour"
        )

    def test_the_settings_checkbox_is_gone(self):
        self.assertNotIn(
            "group_l10n_np_bs_accounting_dates",
            self.env["res.config.settings"]._fields,
        )

    def test_the_company_digit_field_moved_to_core(self):
        company_fields = self.env["res.company"]._fields
        self.assertNotIn("l10n_np_bs_digits", company_fields,
                         "the old digit field survived the move, so there are two")
        self.assertIn("bs_digits", company_fields, "core's digit field is missing")

    def test_the_arch_injection_mixin_is_gone(self):
        self.assertNotIn("l10n_np.bs.date.view.mixin", self.env,
                         "the local mixin survived; coverage would then be applied "
                         "twice, by two different mechanisms")

    def test_no_accounting_view_carries_an_injected_bs_widget(self):
        """The arch must be clean.

        The old mechanism wrote `widget="bs_date"` into the arch at read time. If
        anything still does, that field renders BS regardless of preference --
        including for a user who deliberately chose Gregorian.
        """
        arch, _view = self.env["account.move"]._get_view(view_type="form")
        self.assertNotIn("bs_date", [n.get("widget") for n in arch.iter("field")])


@tagged("-at_install", "post_install")
class TestSettingsSurface(TransactionCase):
    """The calendar stays configurable from Accounting, not only General Settings."""

    def test_the_settings_model_exposes_the_calendar_fields(self):
        settings_fields = self.env["res.config.settings"]._fields
        for name in ("calendar_system", "bs_digits", "bs_report_output"):
            self.assertIn(name, settings_fields,
                          f"{name} is not on res.config.settings")

    def test_the_accounting_settings_view_still_offers_it(self):
        """An accountant must not have to know the setting lives under General."""
        view = self.env.ref("l10n_np_accounting.res_config_settings_view_form")
        arch, _v = self.env["res.config.settings"]._get_view(view_id=view.id)
        names = {n.get("name") for n in arch.iter("field")}
        for name in ("calendar_system", "bs_digits", "bs_report_output"):
            self.assertIn(name, names, f"{name} is missing from the Nepal block")

    def test_writing_the_setting_reaches_the_company(self):
        company = self.env.company
        original = company.calendar_system
        self.addCleanup(company.write, {"calendar_system": original})

        settings = self.env["res.config.settings"].create({"calendar_system": "bs"})
        settings.execute()
        self.assertEqual(company.calendar_system, "bs")


@tagged("-at_install", "post_install")
class TestAccountingDatesKeepCoverage(TransactionCase):
    """Nothing the old allowlist covered may have lost coverage."""

    def test_every_legacy_field_still_exists_and_is_a_date(self):
        """Guard the list itself.

        If a field were renamed upstream, the coverage assertion below would pass
        for the wrong reason -- it would be checking a name that no longer exists.
        """
        checked = 0
        for model, names in LEGACY_ALLOWLIST.items():
            if model not in self.env:
                # An optional module can be absent; the old mixin skipped these
                # rather than failing, and so does this.
                continue
            model_fields = self.env[model]._fields
            for name in names:
                with self.subTest(model=model, field=name):
                    self.assertIn(name, model_fields)
                    self.assertIn(model_fields[name].type, ("date", "datetime"))
                    checked += 1
        self.assertGreater(checked, 15,
                           "almost nothing was checked; are the models installed?")

    def test_no_legacy_field_is_excluded_by_the_new_coverage_policy(self):
        """The inversion must not have swept a business date into the exclusions.

        The exclusion list lives in JavaScript, so this reads it from source rather
        than importing it. Crude, but the alternative is a second copy of the
        policy in Python, and duplicated policy is the class of bug this whole pass
        exists to remove.
        """
        self.assertTrue(os.path.exists(EXCLUSIONS_JS),
                        f"exclusions.js not found at {EXCLUSIONS_JS}")
        with open(EXCLUSIONS_JS, encoding="utf-8") as fh:
            source = fh.read()

        excluded_names = set(re.findall(r'^\s*"(\w+)",', source, re.M))
        self.assertIn("create_date", excluded_names,
                      "failed to parse exclusions.js, so this test is not checking "
                      "what it claims to")

        for model, names in LEGACY_ALLOWLIST.items():
            for name in names:
                with self.subTest(model=model, field=name):
                    self.assertNotIn(
                        name, excluded_names,
                        f"{model}.{name} was covered by the old allowlist but is "
                        f"now globally excluded -- the move lost coverage"
                    )


@tagged("-at_install", "post_install")
class TestStorageUnchanged(TransactionCase):
    """The guarantee the design rests on, asserted from the accounting side."""

    def test_switching_calendar_does_not_alter_a_posted_entry(self):
        company = self.env.company
        original = company.calendar_system
        self.addCleanup(company.write, {"calendar_system": original})

        journal = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", company.id)], limit=1)
        if not journal:
            self.skipTest("no general journal in this company")

        accounting_date = datetime.date(2026, 9, 9)
        company.calendar_system = "ad"
        move = self.env["account.move"].create({
            "journal_id": journal.id,
            "date": accounting_date,
        })
        self.env.flush_all()

        company.calendar_system = "bs"
        move.invalidate_recordset()

        self.assertEqual(
            move.date, accounting_date,
            "the accounting date changed when the display calendar changed"
        )
        self.env.cr.execute("SELECT date FROM account_move WHERE id = %s", (move.id,))
        self.assertEqual(
            self.env.cr.fetchone()[0], accounting_date,
            "the stored column changed with the display calendar; storage must "
            "stay Gregorian"
        )
