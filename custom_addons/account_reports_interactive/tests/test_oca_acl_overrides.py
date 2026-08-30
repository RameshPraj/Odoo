# -*- coding: utf-8 -*-
r"""The vendored OCA grants that were too wide are actually narrowed (SEC-4, SEC-5).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /account_reports_interactive --stop-after-init

Two findings, one mechanism: an override in a local module rather than an edit to
the vendored one, because `VENDORED.md` forbids editing those in place -- the
zero-drift property is what keeps the LIC-1 licence position defensible.

That mechanism is the reason these tests exist rather than a reading of the XML.
Odoo ACLs are a **union**: adding a row can only ever grant more. Narrowing
requires *updating* the vendored row by its fully-qualified xmlid, which works
only if this module loads after that one and only if the record is not
`noupdate`. Both are true here, and neither is visible from the file -- so the
assertion has to be made against a real user's effective rights, not against the
records.

Every check below is written against `base.group_user` alone, because that is the
group the findings name: an ordinary employee with no accounting rights at all.
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestOcaAclOverrides(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A plain employee: base.group_user and nothing else. Built here rather
        # than searched, so the test cannot be weakened by whatever the live
        # database happens to contain (TST-3).
        cls.employee = cls.env["res.users"].create({
            "name": "SEC-5 Employee",
            "login": "sec5.employee",
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
        })
        cls.accountant = cls.env["res.users"].create({
            "name": "SEC-5 Accountant",
            "login": "sec5.accountant",
            "group_ids": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("account.group_account_user").id,
            ])],
        })

    # ---- SEC-5: the aged-balance bucket configuration ---------------------
    def test_an_employee_can_still_read_the_ageing_configuration(self):
        """Read is kept deliberately: the report resolves it while rendering.

        Asserted first, because it is the half a careless fix breaks. Removing
        the grant outright would have looked like a tightening and would have
        broken the Aged Partner Balance for everyone allowed to run it.
        """
        self.env["account.age.report.configuration"].with_user(
            self.employee).search([], limit=1)

    def test_an_employee_cannot_change_the_ageing_configuration(self):
        """The finding: non-accounting staff altering the bucketing everyone reads."""
        config = self.env["account.age.report.configuration"].create({
            "name": "SEC-5 buckets"})
        with self.assertRaises(AccessError):
            config.with_user(self.employee).write({"name": "rewritten"})

    def test_an_employee_cannot_create_or_delete_the_ageing_configuration(self):
        config = self.env["account.age.report.configuration"].create({
            "name": "SEC-5 buckets to delete"})
        with self.assertRaises(AccessError):
            self.env["account.age.report.configuration"].with_user(
                self.employee).create({"name": "invented"})
        with self.assertRaises(AccessError):
            config.with_user(self.employee).unlink()

    def test_an_accountant_can_still_configure_the_ageing_buckets(self):
        """The negative control. Narrowing the vendored row left exactly one grant
        on this model, so without the accountant rows added alongside it the
        configuration would be editable by nobody at all -- a tightening that
        passes every 'employee cannot' assertion above while breaking the feature."""
        config = self.env["account.age.report.configuration"].with_user(
            self.accountant).create({"name": "SEC-5 accountant buckets"})
        config.write({"name": "amended by an accountant"})
        self.assertEqual(config.name, "amended by an accountant")

    # ---- SEC-5: budget lines ----------------------------------------------
    def test_an_employee_cannot_write_budget_lines(self):
        """`access_budget` granted base.group_user 1,1,1,0 on crossovered.budget.lines
        while being named 'manager', and while the accounting ladder was already
        granted properly on the row above it."""
        model = self.env["crossovered.budget.lines"].with_user(self.employee)
        self.assertFalse(
            model.check_access_rights("write", raise_exception=False),
            "an employee must not be able to write budget lines")
        self.assertFalse(
            model.check_access_rights("create", raise_exception=False),
            "an employee must not be able to create budget lines")
        self.assertTrue(
            model.check_access_rights("read", raise_exception=False),
            "read is kept: employee visibility of a budget is plausibly intended "
            "upstream, and it is not what the finding objected to")

    # ---- SEC-4: the wizard default is personal, not company-wide ------------
    #
    # Two halves, and the first draft of this test conflated them. Asserting
    # "no row lacks a user_id" failed on a first run against rows the *old* code
    # had already written -- four of them, one per report anyone had exported.
    # That was the test finding a real thing (stopping the write does not undo
    # it, hence migrations/19.0.1.2.0), but as an assertion it was measuring the
    # database's history rather than this module's behaviour. Split accordingly.
    WIZARD_MODEL = "general.ledger.report.wizard"

    def _label_defaults(self, **extra):
        domain = [("field_id.name", "=", "label_text_limit"),
                  ("field_id.model", "=", self.WIZARD_MODEL)]
        for key, value in extra.items():
            domain.append((key, "=", value))
        return self.env["ir.default"].sudo().search(domain)

    def test_the_remembered_label_limit_is_written_for_the_user_who_set_it(self):
        """The behaviour: a new write belongs to its author, not to everybody."""
        before = self._label_defaults(user_id=self.accountant.id)
        self.assertFalse(before, "fixture assumption: no personal default yet")

        wizard = self.env[self.WIZARD_MODEL].with_user(self.accountant).create({
            "date_from": "2026-07-17", "date_to": "2026-08-31",
            "label_text_limit": 42,
        })
        wizard._set_default_wizard_values()

        mine = self._label_defaults(user_id=self.accountant.id)
        self.assertTrue(
            mine,
            "the wizard must still remember the value, just personally: the fix "
            "narrows who a default applies to, it does not remove the feature")

    def test_exporting_does_not_write_a_default_for_everybody(self):
        """The finding itself: `user_id=False` made every export a company-wide write.

        Measured as a delta, so a company-wide row left over from before the
        migration cannot mask a regression, and cannot fail this either.
        """
        before = set(self._label_defaults(user_id=False).ids)

        wizard = self.env[self.WIZARD_MODEL].with_user(self.accountant).create({
            "date_from": "2026-07-17", "date_to": "2026-08-31",
            "label_text_limit": 7,
        })
        wizard._set_default_wizard_values()

        after = set(self._label_defaults(user_id=False).ids)
        self.assertEqual(
            after - before, set(),
            "an export wrote a default with no user_id, which applies to every "
            "colleague in the company")
