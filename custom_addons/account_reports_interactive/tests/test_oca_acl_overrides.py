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
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged


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


@tagged("-at_install", "post_install")
class TestXlsxRouteAuth(HttpCase):
    """SEC-8: the xlsx report routes must require a logged-in user.

    `report_xlsx` overrode both endpoints with a bare `@route()`, which inherits
    the parent's `auth` rather than declaring one. Core says `auth='user'` today,
    so the assertions below already held before the override -- and that is the
    point. They pin the behaviour so that a change upstream, in a module two
    dependencies away, fails here instead of silently widening access.

    Asserted by calling the endpoint unauthenticated rather than by inspecting
    `original_routing`, because what matters is what the server does with an
    anonymous request, not what the decorator says.
    """

    def _assert_sent_to_login(self, url):
        """The anonymous caller must be turned away by the *auth* layer.

        Asserted as "redirected to /web/login", not as "did not return 200".
        The weaker form was the first draft and is nearly vacuous here: an
        authenticated call to /report/download with no `data` parameter is also
        not a 200, so `assertNotEqual(200)` would have passed with the auth
        pinning removed entirely. Only the login redirect distinguishes being
        rejected for *who you are* from being rejected for *what you sent*.
        """
        response = self.url_open(url, allow_redirects=False)
        self.assertIn(
            response.status_code, (301, 302, 303),
            f"{url} did not redirect an anonymous caller; got "
            f"{response.status_code}")
        self.assertIn(
            "/web/login", response.headers.get("Location", ""),
            f"{url} redirected somewhere other than the login page, so it was "
            f"not the authentication layer that refused the caller")

    def test_report_download_refuses_an_anonymous_caller(self):
        self._assert_sent_to_login("/report/download")

    def test_xlsx_report_route_refuses_an_anonymous_caller(self):
        self._assert_sent_to_login(
            "/report/xlsx/account_financial_report.trial_balance")

    def test_an_authenticated_user_still_reaches_the_route(self):
        """The negative control: pinning auth must not have broken the route.

        A wrong `@route()` override -- restating the paths, or changing `type` --
        would unregister the endpoint, and every assertion above would still
        pass, because a 404 is also "not 200".
        """
        self.authenticate("admin", "admin")
        response = self.url_open("/report/download", allow_redirects=False)
        self.assertNotEqual(
            response.status_code, 404,
            "the endpoint disappeared: the override changed the routing rather "
            "than only pinning auth")


@tagged("-at_install", "post_install")
class TestGeneralLedgerDomain(TransactionCase):
    """SEC-10: a mistyped Journal Items Domain is refused with a sentence.

    The register prescribed swapping `literal_eval` for `safe_eval`. That was not
    done, because measuring the wizard showed `literal_eval` is the *stricter*
    of the two -- it refuses `__import__('os')` outright -- so the swap would
    have widened the field while fixing nothing. The defect it did show is that
    every rejection arrived as an unhandled traceback.
    """

    def _wizard(self, domain):
        return self.env["general.ledger.report.wizard"].create({
            "date_from": "2026-07-17", "date_to": "2026-08-31", "domain": domain,
        })

    def test_a_malformed_domain_is_refused_with_a_message(self):
        for bad in ("[('x','=',1)", "not a domain", "{"):
            with self.subTest(domain=bad):
                with self.assertRaises(UserError) as caught:
                    self._wizard(bad)._get_account_move_lines_domain()
                self.assertIn("not a valid domain", str(caught.exception))

    def test_code_is_still_refused_rather_than_executed(self):
        """The property `literal_eval` already provided, pinned so a later
        well-meaning swap to `safe_eval` cannot quietly widen this field."""
        with self.assertRaises(UserError):
            self._wizard("__import__('os').getcwd()")._get_account_move_lines_domain()

    def test_a_valid_domain_still_parses(self):
        """The negative control: translating the error must not reject good input."""
        parsed = self._wizard("[('partner_id', '!=', False)]")             ._get_account_move_lines_domain()
        self.assertEqual(parsed, [("partner_id", "!=", False)])

    def test_an_empty_domain_is_still_the_empty_list(self):
        self.assertEqual(self._wizard(False)._get_account_move_lines_domain(), [])
