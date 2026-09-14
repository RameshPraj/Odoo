# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Regression tests for Nepal's variable Gregorian fiscal-year boundaries."""

import datetime
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestNepalFiscalYearFinancialReports(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({
            "name": "Nepal financial-report fiscal-year test",
            "country_id": cls.env.ref("base.np").id,
        })
        cls.env["account.fiscal.year"].create({
            "name": "FY 2083/84 (Shrawan-Ashar)",
            "company_id": cls.company.id,
            "date_from": datetime.date(2026, 7, 17),
            "date_to": datetime.date(2027, 7, 16),
        })

    def _assert_opening_start(self, model):
        wizard = self.env[model].new({
            "company_id": self.company.id,
            "date_from": datetime.date(2026, 10, 1),
        })
        wizard._compute_fy_start_date()
        self.assertEqual(
            wizard.fy_start_date,
            datetime.date(2026, 7, 17),
            "opening balances must start at Shrawan 1, not a fixed July date",
        )

    def test_trial_balance_opening_uses_explicit_nepal_fiscal_year(self):
        self._assert_opening_start("trial.balance.report.wizard")

    def test_general_ledger_opening_uses_explicit_nepal_fiscal_year(self):
        self._assert_opening_start("general.ledger.report.wizard")

    def test_general_ledger_defaults_to_exact_nepal_fiscal_year_start(self):
        with patch(
            "odoo.fields.Date.context_today",
            return_value=datetime.date(2026, 10, 1),
        ):
            wizard = self.env["general.ledger.report.wizard"].with_company(
                self.company
            ).new({})
            self.assertEqual(wizard.date_from, datetime.date(2026, 7, 17))
