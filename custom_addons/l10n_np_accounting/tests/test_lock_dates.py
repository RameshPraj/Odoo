# -*- coding: utf-8 -*-
"""Tests for the Lock Dates wizard.

    venv\\Scripts\\python.exe -m odoo -c odoo.conf -d <db> \\
        --test-enable --test-tags /l10n_np_accounting --stop-after-init

Every test uses a company created for the test. Writes to ``res.company`` are
flushed through ``cr.precommit`` and therefore survive ``cr.rollback()``, so
touching the real company here would leave lock dates behind -- and a stray
hard lock date is irreversible.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestLockDates(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Lock Date Test Co"})
        cls.env.user.company_ids = [(4, cls.company.id)]

    def _wizard(self, **values):
        return self.env["account.lock.dates"].create(
            dict(company_id=self.company.id, **values))

    def test_preloads_current_locks(self):
        """The form is an editor, not a blank slate: opening it and pressing
        Apply must not clear a lock that was already set."""
        self.company.fiscalyear_lock_date = "2026-07-15"
        wizard = self.env["account.lock.dates"].with_company(self.company).create({})
        self.assertEqual(str(wizard.fiscalyear_lock_date), "2026-07-15")

    def test_explicit_company_loads_that_company_s_locks(self):
        """Regression: default_get cannot see create() vals, so a wizard created
        for one company used to load env.company's dates. Applying it would then
        have cleared the target company's locks."""
        self.company.fiscalyear_lock_date = "2026-07-15"
        self.assertFalse(self.env.company.fiscalyear_lock_date,
                         "precondition: the ambient company has no global lock")
        wizard = self.env["account.lock.dates"].create({"company_id": self.company.id})
        self.assertEqual(str(wizard.fiscalyear_lock_date), "2026-07-15")

    def test_apply_writes_through(self):
        wizard = self._wizard(fiscalyear_lock_date="2026-07-15",
                              tax_lock_date="2026-07-15")
        wizard.action_apply()
        self.assertEqual(str(self.company.fiscalyear_lock_date), "2026-07-15")
        self.assertEqual(str(self.company.tax_lock_date), "2026-07-15")

    def test_apply_writes_only_what_changed(self):
        """An unchanged hard lock date must not be rewritten, or core's
        irreversibility check would fire on a no-op."""
        self.company.hard_lock_date = "2026-07-15"
        wizard = self._wizard(hard_lock_date="2026-07-15",
                              sale_lock_date="2026-07-31")
        wizard.action_apply()  # must not raise
        self.assertEqual(str(self.company.sale_lock_date), "2026-07-31")
        self.assertEqual(str(self.company.hard_lock_date), "2026-07-15")

    def test_hard_lock_cannot_move_backwards(self):
        """Delegated to core; asserted here so we notice if that ever changes."""
        self.company.hard_lock_date = "2026-07-15"
        wizard = self._wizard(hard_lock_date="2026-06-01")
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_hard_lock_cannot_be_cleared(self):
        self.company.hard_lock_date = "2026-07-15"
        wizard = self._wizard(hard_lock_date=False)
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_switching_company_reloads_its_own_locks(self):
        """A multi-company user must never carry one company's locks onto
        another."""
        other = self.env["res.company"].create({"name": "Other Lock Test Co"})
        self.company.fiscalyear_lock_date = "2026-07-15"
        wizard = self._wizard()
        self.assertEqual(str(wizard.fiscalyear_lock_date), "2026-07-15")
        wizard.company_id = other
        self.assertFalse(wizard.fiscalyear_lock_date)

    def test_non_manager_is_refused(self):
        user = self.env["res.users"].create({
            "name": "Billing Only", "login": "np_lock_test_user",
            "company_id": self.company.id, "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, [self.env.ref("account.group_account_invoice").id])],
        })
        wizard = self._wizard(fiscalyear_lock_date="2026-07-15")
        with self.assertRaises(UserError):
            wizard.with_user(user).action_apply()
