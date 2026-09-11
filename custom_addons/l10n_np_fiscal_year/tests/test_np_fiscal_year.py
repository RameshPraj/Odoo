# -*- coding: utf-8 -*-
"""Tests for Nepali fiscal year generation.

    venv\\Scripts\\python.exe -m odoo -c odoo.conf -d <db> \\
        --test-enable --test-tags /l10n_np_fiscal_year --stop-after-init
"""
import datetime

from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestNPFiscalYear(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Wizard = cls.env["l10n_np.generate.fiscal.year"]
        # A dedicated company per test class. Fiscal years are company-scoped and
        # the generator refuses to overwrite existing ones, so testing against
        # env.company would fail on any database that already has them -- which
        # is exactly what happened once real fiscal years were generated.
        cls.company = cls.env["res.company"].create({
            "name": "FY Test Co",
            "country_id": cls.env.ref("base.np").id,
        })

    def test_known_fiscal_year_ranges(self):
        """Endpoints must match the Bikram Sambat calendar exactly.

        These are the values the generator must produce; they were cross-checked
        against nepali-datetime. Note the end date alternates 15/16 July, which
        is precisely why a fixed fiscalyear_last_day cannot work.
        """
        expected = {
            2082: (datetime.date(2025, 7, 17), datetime.date(2026, 7, 16)),
            2083: (datetime.date(2026, 7, 17), datetime.date(2027, 7, 16)),
            2084: (datetime.date(2027, 7, 17), datetime.date(2028, 7, 15)),
            2085: (datetime.date(2028, 7, 16), datetime.date(2029, 7, 15)),
            2086: (datetime.date(2029, 7, 16), datetime.date(2030, 7, 16)),
        }
        for bs_year, (d1, d2) in expected.items():
            with self.subTest(bs_year=bs_year):
                name, got_from, got_to = self.Wizard._fiscal_year_range(bs_year)
                self.assertEqual(got_from, d1)
                self.assertEqual(got_to, d2)
                self.assertIn(str(bs_year), name)

    def test_end_date_is_not_fixed(self):
        """Guards the core premise: the Gregorian end date varies by year."""
        ends = {self.Wizard._fiscal_year_range(y)[2].day for y in range(2080, 2091)}
        self.assertGreater(
            len(ends), 1,
            "If every year ended on the same day, Odoo's fixed "
            "fiscalyear_last_day would suffice and this module would be pointless.",
        )

    def test_years_are_contiguous(self):
        """No gaps and no overlaps between consecutive fiscal years."""
        prev_to = None
        for y in range(2080, 2091):
            _n, d_from, d_to = self.Wizard._fiscal_year_range(y)
            self.assertLess(d_from, d_to)
            if prev_to is not None:
                self.assertEqual(
                    d_from, prev_to + datetime.timedelta(days=1),
                    f"FY {y} does not start the day after FY {y - 1} ends",
                )
            prev_to = d_to

    def test_generation_creates_records(self):
        wiz = self.Wizard.create({
            "company_id": self.company.id,
            "bs_year_from": 2083,
            "bs_year_to": 2085,
        })
        wiz.action_generate()
        fys = self.env["account.fiscal.year"].search([
            ("company_id", "=", self.company.id),
        ])
        self.assertEqual(len(fys), 3, "expected exactly the three requested years")
        self.assertEqual(
            fys.sorted("date_from")[0].date_from, datetime.date(2026, 7, 17))

    def test_company_fiscal_year_lookup_follows_nepal(self):
        """compute_fiscalyear_dates must return the Nepali year, not Jan-Dec."""
        wiz = self.Wizard.create({
            "company_id": self.company.id,
            "bs_year_from": 2083,
            "bs_year_to": 2084,
        })
        wiz.action_generate()
        info = self.company.compute_fiscalyear_dates(datetime.date(2026, 10, 1))
        self.assertEqual(info["date_from"], datetime.date(2026, 7, 17))
        self.assertEqual(info["date_to"], datetime.date(2027, 7, 16))

    def test_duplicate_generation_is_skipped(self):
        vals = {"company_id": self.company.id, "bs_year_from": 2083, "bs_year_to": 2083}
        self.Wizard.create(vals).action_generate()
        domain = [("company_id", "=", self.company.id)]
        before = self.env["account.fiscal.year"].search_count(domain)
        from odoo.exceptions import UserError  # noqa: PLC0415
        with self.assertRaises(UserError):
            self.Wizard.create(vals).action_generate()
        self.assertEqual(self.env["account.fiscal.year"].search_count(domain), before)

    def test_overwrite_regenerates(self):
        """With 'Replace existing' ticked, regeneration must succeed."""
        vals = {"company_id": self.company.id, "bs_year_from": 2083, "bs_year_to": 2083}
        self.Wizard.create(vals).action_generate()
        self.Wizard.create(dict(vals, overwrite=True)).action_generate()
        self.assertEqual(
            self.env["account.fiscal.year"].search_count(
                [("company_id", "=", self.company.id)]),
            1, "overwrite should replace, not duplicate")
