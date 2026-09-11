# -*- coding: utf-8 -*-
"""Tests for the Nepal TDS framework.

The point of these tests is not that any particular rate is correct -- no rate
ships with this module. They prove the *mechanism* is safe:

  * the table starts empty and says so rather than guessing
  * a rate lookup respects effective dates, so a Finance Act change does not
    retrospectively alter closed periods
  * overlapping rates for the same code are rejected at write time
"""
import datetime
import os

import psycopg2
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@tagged("-at_install", "post_install")
class TestTdsFramework(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Category = cls.env["l10n_np.tds.category"]
        cls.account = cls.env["account.account"].search(
            [("account_type", "=", "liability_current")], limit=1)

    def _cat(self, code, rate, date_from, date_to=False, name=None):
        return self.Category.create({
            "code": code,
            "name": name or f"{code} category",
            "rate": rate,
            "date_from": date_from,
            "date_to": date_to,
            "account_id": self.account.id,
            "company_id": self.company.id,
        })

    # ------------------------------------------------------------------
    # `test_xml_is_well_formed` lived here, in four near-identical copies across
    # four modules, while twelve modules shipping XML had no such test at all
    # (**COD-2**). It moved to `tools/check_xml_wellformed.py`, which `lint` runs.
    #
    # The check needs no ORM, no database and no registry -- it is a filesystem
    # walk and an `lxml` parse -- so paying for a database and a module install to
    # run it was the wrong trade, and a test could only ever cover modules that
    # already had a `tests/` directory. The tool covers all 79 XML files across 16
    # modules, including those with no tests, in about a second.

    def test_ships_with_no_rates(self):
        """Deliberate: rates are law, not code. Shipping a guess would be worse
        than shipping nothing.

        Asserted against **what this module owns**, not against the database being
        empty (**TST-2**). The previous version was
        `assertFalse(self.Category.search_count([]))`, which would begin failing
        permanently the day an accountant entered the first real rate — that is,
        the day the module started doing its job. A test that breaks on correct
        use is worse than no test: it gets deleted, and the assertion it was
        making goes with it.

        `ir.model.data` is the right question because it answers the one actually
        being asked: did *this module's data files* create any rates? An
        accountant's records have no xmlid and are invisible here.
        """
        shipped = self.env["ir.model.data"].search_count([
            ("model", "=", "l10n_np.tds.category"),
            ("module", "=", "l10n_np_tds"),
        ])
        self.assertEqual(
            shipped, 0,
            "This module must not ship TDS rates. Rates are set by the Income Tax "
            "Act and entered by an accountant.",
        )

    def test_missing_rate_raises_clear_error(self):
        with self.assertRaises(UserError) as ctx:
            self.Category._rate_for_date("RENT", datetime.date(2026, 8, 1))
        self.assertIn("No TDS rate is configured", str(ctx.exception))

    def test_rate_lookup_respects_effective_dates(self):
        """The core guarantee: a later rate must not alter an earlier period."""
        self._cat("RENT", 10.0, "2025-07-17", "2026-07-16", name="Rent (old)")
        self._cat("RENT", 12.0, "2026-07-17", name="Rent (current)")

        old = self.Category._rate_for_date("RENT", datetime.date(2026, 1, 15))
        new = self.Category._rate_for_date("RENT", datetime.date(2026, 9, 15))
        self.assertEqual(old.rate, 10.0, "a past date must resolve to the past rate")
        self.assertEqual(new.rate, 12.0, "a current date must resolve to the new rate")

    def test_overlapping_rates_rejected(self):
        self._cat("SERV", 15.0, "2026-07-17")
        with self.assertRaises(ValidationError):
            self._cat("SERV", 20.0, "2026-10-01")

    def test_adjacent_rates_allowed(self):
        """Closing one rate the day before the next starts must be accepted."""
        self._cat("SERV", 15.0, "2025-07-17", "2026-07-16")
        later = self._cat("SERV", 20.0, "2026-07-17")
        self.assertTrue(later.id)

    def test_date_order_validated(self):
        with self.assertRaises(ValidationError):
            self._cat("BAD", 5.0, "2026-08-31", "2026-07-01")

    def test_negative_rate_rejected(self):
        # CheckViolation, not Exception: see the same fix in l10n_np_loan's tests
        # and audit finding COD-7. A bare `Exception` here would pass on a
        # misspelled helper name just as happily as on the constraint firing.
        with self.assertRaises(psycopg2.errors.CheckViolation):
            self._cat("NEG", -5.0, "2026-07-17")

    def test_certificate_requires_lines_before_issue(self):
        partner = self.env["res.partner"].create({"name": "TDS Payee"})
        cert = self.env["l10n_np.tds.certificate"].create({
            "partner_id": partner.id,
            "date_from": "2026-07-17",
            "date_to": "2026-08-31",
            "company_id": self.company.id,
        })
        self.assertNotEqual(cert.name, "New", "sequence should assign a number")
        with self.assertRaises(UserError):
            cert.action_issue()

    def test_is_configured_flag(self):
        """`_is_configured` is company-scoped, so test it on a company of our own.

        The previous version called `_is_configured()` with no argument, which
        answers for `env.company` — and asserted False, so it depended on the
        live company having no TDS categories. It would fail the moment one was
        configured (**TST-2**). A fresh company has none by construction, which
        makes the assertion true for the right reason instead of by accident.
        """
        company = self.env["res.company"].create({"name": "TDS Config Test Co"})
        self.assertFalse(
            self.Category._is_configured(company),
            "a company with no categories must read as unconfigured")

        self.Category.create({
            "code": "ANY", "name": "ANY category", "rate": 1.5,
            "date_from": "2026-07-17", "account_id": self.account.id,
            "company_id": company.id,
        })
        self.assertTrue(
            self.Category._is_configured(company),
            "one category is enough to count as configured")

        # And it must stay per-company: configuring one must not configure another.
        other = self.env["res.company"].create({"name": "TDS Unconfigured Co"})
        self.assertFalse(
            self.Category._is_configured(other),
            "configuring one company must not mark another as configured")
