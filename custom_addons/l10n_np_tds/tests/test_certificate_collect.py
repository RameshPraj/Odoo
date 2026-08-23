# -*- coding: utf-8 -*-
r"""``action_collect_lines`` against a real withholding line (TST-5).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_tds --stop-after-init

This is the only code path that puts a figure on a statutory certificate handed to
a payee, and it had no test. It also did not work: it searched
``account.withholding.line``, an **AbstractModel** whose table does not exist, and
a bare ``except Exception`` reported the resulting ``UndefinedTable`` as "Check
that 'l10n_account_withholding_tax' is installed" -- about a module that is
installed. Verified by running it: ``search()`` on that model raises
``UndefinedTable: relation "account_withholding_line" does not exist``.

Everything here therefore goes through a **real posted payment carrying a real
withholding line**, never a hand-made ``l10n_np.tds.certificate.line``. A test that
built the lines itself would only assert that the certificate can add up, which
was never in doubt, and would have stayed green through all of the above -- the
same mistake as FIN-2's statement tests, which called ``_get_report_values()`` and
never rendered anything.

Everything is built on a company created for the test. Writes to ``res.company``
are flushed through ``cr.precommit`` and survive ``cr.rollback()``, so setting
``withholding_tax_base_account_id`` on the real company would leave that
configuration behind after the suite -- the hazard ``test_lock_dates.py``
documents. The cost is that a company with no chart of accounts supplies none of
its accounting wiring, which is what ``setUpClass`` is building by hand.
"""
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCertificateCollect(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        nepal = cls.env.ref("base.np")
        cls.company = cls.env["res.company"].create({
            "name": "TST-5 Withholding Co", "country_id": nepal.id})
        cls.env = cls.env(context=dict(
            cls.env.context, allowed_company_ids=[cls.company.id]))

        # A chartless company supplies none of this, and a payment cannot post
        # without all of it.
        cls.company.withholding_tax_base_account_id = cls._account(
            "WTHB", "Withholding base", "asset_current", reconcile=True)
        cls.journal = cls.env["account.journal"].create({
            "name": "Bank", "code": "TST5B", "type": "bank",
            "company_id": cls.company.id,
            "default_account_id": cls._account("1101", "Bank", "asset_cash").id,
        })
        cls.journal.outbound_payment_method_line_ids.payment_account_id = cls._account(
            "1102", "Outstanding payments", "asset_current")
        payable = cls._account("2100", "Payable", "liability_payable", reconcile=True)

        cls.wth_tax = cls.env["account.tax"].create({
            "name": "TDS 10%", "amount_type": "percent", "amount": -10.0,
            "type_tax_use": "purchase", "company_id": cls.company.id,
            "country_id": nepal.id,
            "tax_group_id": cls.env["account.tax.group"].create({
                "name": "TDS", "company_id": cls.company.id}).id,
            # The two flags that make this a withholding tax rather than merely a
            # negative purchase tax: withheld at payment, and separately numbered.
            "is_withholding_tax_on_payment": True,
            "withholding_sequence_id": cls.env["ir.sequence"].create({
                "name": "TST-5 withholding", "implementation": "no_gap",
                "padding": 4, "number_increment": 1}).id,
        })

        cls.payee = cls.env["res.partner"].create({"name": "TST-5 Payee"})
        cls.other_payee = cls.env["res.partner"].create({"name": "TST-5 Other Payee"})
        for partner in (cls.payee, cls.other_payee):
            partner.with_company(cls.company).property_account_payable_id = payable

    @classmethod
    def _account(cls, code, name, account_type, reconcile=False):
        return cls.env["account.account"].create({
            "code": code, "name": name, "account_type": account_type,
            "reconcile": reconcile,
            "company_ids": [Command.set([cls.company.id])],
        })

    def _payment(self, partner, base=100_000.0, date="2026-08-01", post=True):
        """A supplier payment carrying one withholding line, as the ledger holds it."""
        payment = self.env["account.payment"].with_company(self.company).create({
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": partner.id,
            "amount": base,
            "date": date,
            "journal_id": self.journal.id,
            "company_id": self.company.id,
            "withholding_line_ids": [Command.create({
                "tax_id": self.wth_tax.id,
                "base_amount": base,
            })],
        })
        if post:
            payment.action_post()
        return payment

    def _certificate(self, partner, date_from="2026-07-16", date_to="2027-07-15"):
        return self.env["l10n_np.tds.certificate"].with_company(self.company).create({
            "partner_id": partner.id,
            "company_id": self.company.id,
            "date_from": date_from,
            "date_to": date_to,
        })

    # ------------------------------------------------------------------
    def test_it_collects_the_amount_actually_withheld(self):
        """The failure this finding is named for: a certificate reporting zero.

        Before the fix this raised UserError before reaching any figure at all.
        """
        self._payment(self.payee)
        cert = self._certificate(self.payee)
        cert.action_collect_lines()

        self.assertTrue(cert.line_ids, "no line was collected")
        self.assertEqual(cert.amount_base, 100_000.0)
        self.assertEqual(cert.amount_tds, 10_000.0,
                         "the certificate must report the 10% actually withheld, "
                         "not zero")

    def test_it_does_not_collect_another_payees_withholding(self):
        """There is no ``partner_id`` on a withholding line, so the old
        ``'partner_id' in l._fields`` test was always False and the filter degraded
        to ``True``. Every payee's withholding would have landed on one payee's
        certificate: a disclosure of a third party's tax affairs on a document
        handed to someone else, as well as a wrong total."""
        self._payment(self.payee, base=100_000.0)
        self._payment(self.other_payee, base=500_000.0)

        cert = self._certificate(self.payee)
        cert.action_collect_lines()

        self.assertEqual(len(cert.line_ids), 1)
        self.assertEqual(cert.amount_base, 100_000.0,
                         "another payee's withholding leaked onto this certificate")
        self.assertEqual(cert.amount_tds, 10_000.0)

    def test_it_stamps_the_payment_date_not_the_period_end(self):
        """There is no ``date`` on a withholding line either, and ``comodel_date``
        is computed and unstored, so it cannot even appear in a domain. Every line
        used to be stamped with the period end."""
        self._payment(self.payee, date="2026-08-01")
        cert = self._certificate(self.payee, date_to="2027-07-15")
        cert.action_collect_lines()

        self.assertEqual(str(cert.line_ids[0].date), "2026-08-01")

    def test_it_cites_the_withholding_sequence_number(self):
        """A certificate has to be traceable to the withholding it reports."""
        self._payment(self.payee)
        cert = self._certificate(self.payee)
        cert.action_collect_lines()

        self.assertTrue(cert.line_ids[0].name)
        self.assertNotIn("account.payment.withholding.line",
                         cert.line_ids[0].name,
                         "the line is named by its ORM repr, not by its sequence")

    def test_a_draft_payment_is_not_on_the_certificate(self):
        """A draft payment has withheld nothing. A certificate claiming otherwise
        overstates the credit the payee may claim from the IRD."""
        self._payment(self.payee, post=False)
        cert = self._certificate(self.payee)
        with self.assertRaises(UserError):
            cert.action_collect_lines()

    def test_a_payment_outside_the_period_is_not_collected(self):
        self._payment(self.payee, date="2026-08-01")
        cert = self._certificate(self.payee,
                                 date_from="2026-09-01", date_to="2026-09-30")
        with self.assertRaises(UserError):
            cert.action_collect_lines()

    def test_collecting_twice_does_not_double_the_figures(self):
        self._payment(self.payee)
        cert = self._certificate(self.payee)
        cert.action_collect_lines()
        cert.action_collect_lines()
        self.assertEqual(len(cert.line_ids), 1)
        self.assertEqual(cert.amount_tds, 10_000.0)

    def test_issuing_without_collecting_is_refused(self):
        cert = self._certificate(self.payee)
        with self.assertRaises(UserError):
            cert.action_issue()
