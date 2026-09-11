# -*- coding: utf-8 -*-
r"""'Replace existing' may only replace what this wizard created (BS-15).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_fiscal_year --stop-after-init

`action_generate` searched for overlapping `account.fiscal.year` records by
**company and dates only**, then called `overlapping.unlink()`. Ticking "Replace
existing" therefore deleted every fiscal year overlapping the requested span,
including ones a site entered by hand and any owned by the OCA
`account_fiscal_year` module. Nothing named what was about to go, and unlinking a
fiscal year cannot be undone from the UI.

The tests come in pairs on purpose. A fix that simply refused to delete anything
would satisfy every "it survived" assertion while quietly breaking the feature,
so each protection check is matched by a control proving the wizard still does
its job.
"""
import datetime

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestOverwriteScope(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Wizard = cls.env["l10n_np.generate.fiscal.year"]
        cls.FiscalYear = cls.env["account.fiscal.year"]
        # A dedicated company, for the reason given in test_np_fiscal_year.py:
        # fiscal years are company-scoped and the live company may already have
        # them.
        cls.company = cls.env["res.company"].create({
            "name": "BS-15 Test Co",
            "country_id": cls.env.ref("base.np").id,
        })
        # BS 2083 runs 2026-07-17 to 2027-07-16.
        cls.bs_year = 2083
        cls.name, cls.date_from, cls.date_to = cls.Wizard._fiscal_year_range(cls.bs_year)

    def _wizard(self, overwrite=True):
        return self.Wizard.create({
            "company_id": self.company.id,
            "bs_year_from": self.bs_year,
            "bs_year_to": self.bs_year,
            "overwrite": overwrite,
        })

    def _foreign_year(self, name="Board Year 2026-27"):
        """A fiscal year this wizard did not create, overlapping the same span."""
        return self.FiscalYear.create({
            "name": name,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_id": self.company.id,
        })

    # ---- the finding -------------------------------------------------------
    def test_a_year_this_wizard_did_not_create_survives(self):
        """The data loss. Previously this record was unlinked without mention."""
        foreign = self._foreign_year()

        with self.assertRaises(UserError) as caught:
            self._wizard().action_generate()

        self.assertTrue(
            foreign.exists(),
            "a fiscal year the wizard did not create was deleted by 'Replace "
            "existing'")
        self.assertIn(
            "Board Year 2026-27", str(caught.exception),
            "the refusal must name the record standing in the way, or the user "
            "cannot act on it")

    def test_the_refusal_says_what_to_do(self):
        self._foreign_year()
        with self.assertRaises(UserError) as caught:
            self._wizard().action_generate()
        message = str(caught.exception)
        self.assertIn("Rename or remove them first", message)

    # ---- the controls ------------------------------------------------------
    def test_a_year_this_wizard_created_is_still_replaced(self):
        """The positive control: refusing everything is not a fix."""
        self._wizard().action_generate()
        first = self.FiscalYear.search([
            ("company_id", "=", self.company.id), ("name", "=", self.name)])
        self.assertEqual(len(first), 1, "the wizard did not generate its year")

        self._wizard().action_generate()

        second = self.FiscalYear.search([
            ("company_id", "=", self.company.id), ("name", "=", self.name)])
        self.assertEqual(len(second), 1, "replacing produced a duplicate")
        self.assertNotEqual(
            second.id, first.id,
            "'Replace existing' did not actually replace the wizard's own year")

    def test_generation_still_works_on_a_clean_company(self):
        self._wizard(overwrite=False).action_generate()
        created = self.FiscalYear.search([
            ("company_id", "=", self.company.id), ("name", "=", self.name)])
        self.assertEqual(len(created), 1)
        self.assertEqual(created.date_from, self.date_from)
        self.assertEqual(created.date_to, self.date_to)

    def test_a_non_overlapping_foreign_year_is_left_alone_and_does_not_block(self):
        """Scope check: only *overlapping* records were ever at risk."""
        elsewhere = self.FiscalYear.create({
            "name": "Board Year 2020-21",
            "date_from": datetime.date(2020, 1, 1),
            "date_to": datetime.date(2020, 12, 31),
            "company_id": self.company.id,
        })
        self._wizard().action_generate()
        self.assertTrue(elsewhere.exists())

    # ---- the pattern and the builder must agree ----------------------------
    def test_the_name_pattern_matches_what_the_wizard_builds(self):
        """`_GENERATED_NAME` decides what may be deleted, and it is written out
        separately from `_fiscal_year_range`, which builds the names. Two
        sources of truth for one format, so something has to compare them."""
        from ..wizard.generate_np_fiscal_year import _GENERATED_NAME

        for bs_year in (1975, 2083, 2099):
            name, _from, _to = self.Wizard._fiscal_year_range(bs_year)
            self.assertTrue(
                _GENERATED_NAME.match(name),
                f"the wizard builds {name!r} but its own pattern does not match "
                f"it, so it would refuse to replace its own fiscal years")

    def test_the_pattern_does_not_claim_a_stranger_s_year(self):
        from ..wizard.generate_np_fiscal_year import _GENERATED_NAME

        for name in ("Board Year 2026-27", "FY 2083/84", "Calendar 2026",
                     "My FY 2083/84 (Shrawan-Ashar)"):
            self.assertFalse(
                _GENERATED_NAME.match(name),
                f"{name!r} would be treated as this wizard's own and deleted")
