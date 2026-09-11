# -*- coding: utf-8 -*-
r"""One certificate series per company, not one for the whole database (ACC-6).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_tds --stop-after-init

The module shipped a single `ir.sequence` with `company_id = False`.
`next_by_code` matches `company_id in (False, env.company.id)`, so every company
drew from that one row: a certificate issued by one company advanced the
numbering of all the others.

A TDS certificate is a statutory document handed to a payee and filed with the
IRD, and its number is how that filing is referenced. A series shared across
issuers is wrong on its own terms, and it is also the shape the SAAS findings
describe -- shared mutable state, invisible with one company and wrong the
moment there are two.

These assert the numbering, not the sequence records: what matters is the number
a certificate ends up carrying, and asserting on `ir.sequence` rows would pass
just as well if `create()` never consulted them.
"""
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCertificateSequenceIsPerCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "ACC-6 Co A"})
        cls.company_b = cls.env["res.company"].create({"name": "ACC-6 Co B"})
        cls.partner = cls.env["res.partner"].create({"name": "ACC-6 Payee"})

    def _certificate(self, company):
        return self.env["l10n_np.tds.certificate"].create({
            "partner_id": self.partner.id,
            "company_id": company.id,
            "date_from": "2026-07-17",
            "date_to": "2026-08-31",
        })

    @staticmethod
    def _counter(name):
        """The numeric tail of `TDS/<year>/0001`."""
        return int(name.rsplit("/", 1)[1])

    def test_two_companies_number_independently(self):
        """The defect itself. Under one global sequence these interleave."""
        a1 = self._certificate(self.company_a)
        b1 = self._certificate(self.company_b)
        a2 = self._certificate(self.company_a)

        self.assertEqual(
            self._counter(a2.name), self._counter(a1.name) + 1,
            f"company A's series must not be advanced by company B: "
            f"{a1.name} then {a2.name}, with {b1.name} issued in between")

    def test_each_company_starts_its_own_series(self):
        """A company issuing for the first time gets its own counter, not the
        next number of whatever series happened to exist."""
        b1 = self._certificate(self.company_b)
        self.assertEqual(
            self._counter(b1.name), 1,
            f"a company's first certificate should be number 1, got {b1.name}")

    def test_the_certificates_company_wins_over_the_active_one(self):
        """The case `next_by_code`'s implicit `env.company` gets wrong.

        A multi-company user creating a certificate *for* another company is
        exactly when a number drawn from the wrong series would be least likely
        to be noticed, so the fix keys on `vals['company_id']`.
        """
        # Active company is A; the certificate belongs to B.
        made_in_a_context = self.env["l10n_np.tds.certificate"].with_company(
            self.company_a).create({
                "partner_id": self.partner.id,
                "company_id": self.company_b.id,
                "date_from": "2026-07-17",
                "date_to": "2026-08-31",
            })
        self.assertEqual(made_in_a_context.company_id, self.company_b)
        self.assertEqual(
            self._counter(made_in_a_context.name), 1,
            "the number came from the active company's series rather than the "
            "certificate's own")

    def test_a_company_with_no_sequence_yet_can_still_issue(self):
        """The lazy-create path: a company created after install has no series
        shipped for it, and must get one rather than an error or a blank name."""
        late = self.env["res.company"].create({"name": "ACC-6 Late Co"})
        self.assertFalse(
            self.env["ir.sequence"].sudo().search([
                ("code", "=", "l10n_np.tds.certificate"),
                ("company_id", "=", late.id),
            ]), "fixture assumption: no series exists for this company yet")

        certificate = self._certificate(late)

        self.assertNotEqual(certificate.name, "New")
        self.assertTrue(certificate.name.startswith("TDS/"))
        self.assertTrue(
            self.env["ir.sequence"].sudo().search([
                ("code", "=", "l10n_np.tds.certificate"),
                ("company_id", "=", late.id),
            ]), "issuing should have created the company's series")

    def test_the_shipped_sequence_belongs_to_a_company(self):
        """No company-less row may remain: one would be matched by every
        company's `next_by_code` and reintroduce the shared counter."""
        orphans = self.env["ir.sequence"].sudo().search([
            ("code", "=", "l10n_np.tds.certificate"),
            ("company_id", "=", False),
        ])
        self.assertFalse(
            orphans,
            "a company-less TDS certificate sequence still exists; every "
            "company would draw from it")
