# -*- coding: utf-8 -*-
r"""The box formula grammar (SEC-3) and who may rewrite a return (SEC-6).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_vat_return --stop-after-init

SEC-3 was a denial of service, not a code-execution hole: the old whitelist was
``re.fullmatch(r"[0-9eE+\-*/(). ]*")``, and a character class cannot express "one
star but not two", so ``**`` passed and ``9**9**9`` went to ``eval``. With
``workers = 0`` that occupies the whole server, and ``limit_time_real = 0`` on this
host means nothing reclaims it. The evaluator now parses and walks the expression
instead, so ``ast.Pow`` is simply not in the allowed set.

The exponentiation test below deliberately does **not** evaluate ``9**9**9``. A
test that hangs the runner to prove a hang was fixed is a test nobody can run; it
asserts the refusal instead, which is the behaviour that matters, and the docstring
records what the old code did with the same input.
"""
from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestFormulaGrammar(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.form = cls.env["l10n_np.vat.return.form"].create({
            "name": "SEC-3 form", "company_id": cls.company.id,
            "date_from": "2026-07-16",
        })
        cls.vat_return = cls.env["l10n_np.vat.return"].create({
            "name": "SEC-3 return", "company_id": cls.company.id,
            "date_from": "2026-07-16", "date_to": "2026-08-16",
        })

    def _box(self, code, formula):
        return self.env["l10n_np.vat.return.box"].create({
            "form_id": self.form.id, "code": code, "label_en": code,
            "box_type": "formula", "formula": formula,
        })

    def _eval(self, formula, values=None):
        return self.vat_return._eval_formula(
            self._box("Z", formula), values if values is not None else {})

    # ---- the grammar still works --------------------------------------
    def test_arithmetic_still_evaluates(self):
        """The point of a whitelist is that the allowed things work."""
        for formula, expected in (
            ("1 + 2", 3.0),
            ("10 - 4", 6.0),
            ("3 * 4", 12.0),
            ("10 / 4", 2.5),
            ("(1 + 2) * 3", 9.0),
            ("-5 + 1", -4.0),
            ("2 + 3 * 4", 14.0),
        ):
            with self.subTest(formula=formula):
                self.assertEqual(self._eval(formula), expected)

    def test_box_codes_are_substituted(self):
        self.assertEqual(self._eval("11 - 21", {"11": 500.0, "21": 200.0}), 300.0)

    def test_a_code_is_not_matched_inside_a_longer_number(self):
        """The old sequential ``str.replace`` could rewrite digits inside a float it
        had already substituted: with a box coded '0', an earlier '200.0' became
        '2<substitution>0.0'. Substitution is now a single pass with boundaries."""
        self.assertEqual(self._eval("11 + 0", {"11": 200.0, "0": 5.0}), 205.0)

    # ---- and the disallowed things do not ------------------------------
    def test_exponentiation_is_refused(self):
        """SEC-3 itself. ``9**9**9`` passed the old regex and was handed to
        ``eval``, which then occupied the worker computing a number with hundreds
        of millions of digits. Not evaluated here on purpose -- see the module
        docstring."""
        for formula in ("9**9", "2 ** 8", "9**9**9"):
            with self.subTest(formula=formula):
                with self.assertRaises(UserError):
                    self._eval(formula)

    def test_names_and_calls_are_refused(self):
        for formula in ("__import__('os')", "print(1)", "x + 1", "[1,2]",
                        "1 if 1 else 2", "1 == 1", "'a' * 3"):
            with self.subTest(formula=formula):
                with self.assertRaises(UserError):
                    self._eval(formula)

    def test_division_by_zero_is_a_message_not_a_traceback(self):
        with self.assertRaises(UserError):
            self._eval("1 / 0")

    def test_an_unresolved_box_code_is_named_in_the_error(self):
        """A formula referring to a box that no longer exists must say which."""
        with self.assertRaises(UserError) as caught:
            self._eval("total + 1")
        self.assertIn("total", str(caught.exception))

    def test_a_formula_box_cannot_have_no_formula(self):
        """Written the other way round after the first attempt asserted that an
        empty formula evaluates to 0.0 -- which it does, but the model's own
        `_check_definition` constraint means such a box cannot be created, so that
        branch is unreachable and the assertion was testing nothing real. The
        constraint is the behaviour worth locking in."""
        with self.assertRaises(ValidationError):
            self._box("EMPTY", "")


@tagged("-at_install", "post_install")
class TestReturnLineAccess(TransactionCase):
    """SEC-6: the read-only accounting role could rewrite a filed return's figures.

    The ACL granted ``account.group_account_readonly`` write, create **and**
    unlink on ``l10n_np.vat.return.line`` -- inconsistent with the same file's own
    read-only rows for the form and the box. Because every higher accounting group
    implies the read-only one, that row was also what granted everyone else their
    access, so it could not simply be set to ``1,0,0,0``: computing a return
    unlinks and recreates its lines, so the billing role needed its own row.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.vat_return = cls.env["l10n_np.vat.return"].create({
            "name": "SEC-6 return", "company_id": cls.company.id,
            "date_from": "2026-07-16", "date_to": "2026-08-16",
        })
        cls.line = cls.env["l10n_np.vat.return.line"].create({
            "return_id": cls.vat_return.id, "code": "11",
            "label_en": "Taxable sales", "amount": 100_000.0,
        })

        def user(login, group):
            return cls.env["res.users"].create({
                "name": login, "login": login,
                "company_id": cls.company.id,
                "company_ids": [Command.set([cls.company.id])],
                "group_ids": [Command.set([cls.env.ref(group).id])],
            })

        cls.readonly_user = user("sec6_readonly", "account.group_account_readonly")
        cls.billing_user = user("sec6_billing", "account.group_account_invoice")

    def test_the_readonly_role_can_read_a_return_line(self):
        """It is a read-only role, not a no-access role. This is the assertion that
        stops the fix being 'remove the row'."""
        self.assertEqual(
            self.line.with_user(self.readonly_user).read(["amount"])[0]["amount"],
            100_000.0)

    def test_the_readonly_role_cannot_rewrite_a_figure(self):
        """SEC-6. Rewriting `amount` changes what was filed with the IRD."""
        with self.assertRaises(AccessError):
            self.line.with_user(self.readonly_user).write({"amount": 0.0})

    def test_the_readonly_role_cannot_delete_a_line(self):
        with self.assertRaises(AccessError):
            self.line.with_user(self.readonly_user).unlink()

    def test_the_readonly_role_cannot_add_a_line(self):
        with self.assertRaises(AccessError):
            self.env["l10n_np.vat.return.line"].with_user(
                self.readonly_user).create({
                    "return_id": self.vat_return.id, "code": "99",
                    "label_en": "Invented", "amount": 1.0})

    def test_the_billing_role_can_still_maintain_lines(self):
        """`action_compute` unlinks and recreates every line, so whoever may
        compute a return must be able to do both. Tightening the read-only row
        without adding this one would have broken computation instead."""
        as_billing = self.env["l10n_np.vat.return.line"].with_user(self.billing_user)
        created = as_billing.create({
            "return_id": self.vat_return.id, "code": "12",
            "label_en": "Exports", "amount": 5.0})
        created.write({"amount": 6.0})
        self.assertEqual(created.amount, 6.0)
        created.unlink()

    def test_a_filed_return_cannot_be_silently_recomputed(self):
        """Found while fixing SEC-6, and the same document is at stake.
        `action_compute` checked no state, so a filed return could be recomputed
        in place and the filed figures would change with no trace."""
        self.vat_return.state = "filed"
        with self.assertRaises(UserError):
            self.vat_return.action_compute()
