# -*- coding: utf-8 -*-
r"""The Matching column says what it means (matching_status / matching_label).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_accounting --stop-after-init

Core's Matching column shows `matching_number`, a token that is the
`account.full.reconcile` primary key when fully matched, `P<n>` when partial,
`I<x>` when merely *marked* to be matched once its moves post, and empty
otherwise. On the live database that rendered as `37`/`38` on four rows and blank
on twenty -- and the blanks conflated "this account can never be reconciled" with
"this is reconcilable and still owed".

Every state below is built from a real reconciliation rather than by assigning
the fields, because the fields are computed from partials and asserting on
hand-set values would test nothing. Two of the five states -- `partial` and
`pending_post` -- do not occur anywhere in this database, so they are created
here on purpose: a test that quietly finds nothing to assert on is the failure
mode this project has already been bitten by four times (TST-1, TST-2, TST-3,
TST-9).

Fixtures are searched-then-created, never searched-then-skipped, for the same
reason (TST-3).
"""
import os
import re

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestMatchingColumn(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create({"name": "Matching Test Partner"})
        cls.journal = cls._journal()
        cls.receivable = cls._account(
            "asset_receivable", "MTCRECV", "Matching test receivable", reconcile=True)
        cls.income = cls._account("income", "MTCINC", "Matching test income")

    @classmethod
    def _account(cls, account_type, code, name, reconcile=False):
        domain = [("account_type", "=", account_type),
                  ("company_ids", "in", cls.env.company.id)]
        if reconcile:
            domain.append(("reconcile", "=", True))
        return cls.env["account.account"].search(domain, limit=1) or \
            cls.env["account.account"].create({
                "code": code, "name": name, "account_type": account_type,
                "reconcile": reconcile,
                "company_ids": [Command.set([cls.env.company.id])],
            })

    @classmethod
    def _journal(cls):
        return cls.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", cls.env.company.id)],
            limit=1) or cls.env["account.journal"].create({
                "name": "Matching Test Journal", "code": "MTCJ",
                "type": "general", "company_id": cls.env.company.id,
            })

    def _entry(self, amount, debit_side=True, date="2026-08-10"):
        """One posted two-line entry: receivable against income."""
        rec_vals = {"debit": amount, "credit": 0.0} if debit_side \
            else {"debit": 0.0, "credit": amount}
        inc_vals = {"debit": 0.0, "credit": amount} if debit_side \
            else {"debit": amount, "credit": 0.0}
        move = self.env["account.move"].create({
            "move_type": "entry", "date": date, "journal_id": self.journal.id,
            "line_ids": [
                Command.create({"account_id": self.receivable.id, "name": "recv",
                                "partner_id": self.partner.id, **rec_vals}),
                Command.create({"account_id": self.income.id, "name": "inc",
                                "partner_id": self.partner.id, **inc_vals}),
            ],
        })
        move.action_post()
        return move

    def _receivable_line(self, move):
        return move.line_ids.filtered(lambda aml: aml.account_id == self.receivable)

    # ---- the five states -------------------------------------------------
    def test_a_line_on_a_non_reconcilable_account_says_so(self):
        """The state that used to be an empty cell indistinguishable from 'open'.

        This is the case in the reported URL: line 1118 sits on Sales Revenue, an
        income account, so it can never be matched and its Matching cell was
        permanently blank for a reason the reader could not see.
        """
        move = self._entry(100.0)
        income_line = move.line_ids.filtered(lambda aml: aml.account_id == self.income)

        self.assertEqual(income_line.matching_status, "not_reconcilable")
        self.assertEqual(
            income_line.matching_label, "",
            "the label is empty by design; the widget draws the dash, so an "
            "exported file does not carry punctuation pretending to be data")

    def test_an_unmatched_reconcilable_line_shows_what_is_still_open(self):
        """The only actionable state in this column, and previously also blank."""
        line = self._receivable_line(self._entry(150.0))

        self.assertEqual(line.matching_status, "open")
        self.assertIn("Open", line.matching_label)
        self.assertIn("150", line.matching_label,
                      f"the residual must appear: {line.matching_label!r}")

    def test_a_fully_matched_line_names_its_counterpart(self):
        """Replaces the bare full-reconcile primary key with the document name."""
        debit_move = self._entry(80.0, debit_side=True)
        credit_move = self._entry(80.0, debit_side=False)
        lines = self._receivable_line(debit_move) + self._receivable_line(credit_move)
        lines.reconcile()

        line = self._receivable_line(debit_move)
        self.assertEqual(line.matching_status, "matched")
        self.assertIn("Matched", line.matching_label)
        self.assertIn(
            credit_move.name, line.matching_label,
            f"the counterpart entry must be named, not its id: "
            f"{line.matching_label!r}")
        # And the raw token is still there for anything that depends on it.
        self.assertTrue(line.matching_number)
        self.assertEqual(line.matching_number, str(line.full_reconcile_id.id))

    def test_a_partially_matched_line_shows_both_numbers(self):
        """Created here because no partial match exists in this database.

        Reconciling 80.00 against 30.00 leaves 50.00 outstanding, so core writes
        a `P<n>` token and no full reconcile. The old column showed `P12`; this
        shows what was matched and what is left.
        """
        big = self._entry(80.0, debit_side=True)
        small = self._entry(30.0, debit_side=False)
        lines = self._receivable_line(big) + self._receivable_line(small)
        lines.reconcile()

        line = self._receivable_line(big)
        self.assertEqual(
            line.matching_status, "partial",
            f"expected a partial match; matching_number={line.matching_number!r}")
        self.assertTrue(line.matching_number.startswith("P"),
                        "fixture assumption: core marks partials with a P prefix")
        self.assertIn("Partial", line.matching_label)
        self.assertIn(small.name, line.matching_label,
                      "a partial match must still name what it was matched with")
        self.assertIn("50", line.matching_label,
                      f"the 50.00 still open must appear: {line.matching_label!r}")

    def test_a_marked_line_is_not_reported_as_matched(self):
        """The `I` prefix, which the raw column renders as if it were a match.

        `_sanitize_vals` (account/models/account_move_line.py:1699-1704) forces an
        `I` prefix onto any externally written matching number, marking lines to
        be reconciled once their moves post. In the raw column that looks like a
        match. It is not one, and this is the state most likely to mislead.
        """
        line = self._receivable_line(self._entry(60.0))
        line.matching_number = "12345"

        self.assertTrue(
            line.matching_number.startswith("I"),
            f"fixture assumption: core prefixes with I, got "
            f"{line.matching_number!r}")
        self.assertEqual(line.matching_status, "pending_post")
        self.assertNotIn("Matched", line.matching_label)
        self.assertIn("not yet", line.matching_label)

    # ---- the properties the design promised -------------------------------
    def test_the_label_survives_an_export(self):
        """The whole reason the label is a server-side field and not JavaScript.

        A JS-only widget would leave an XLSX export and a printed list showing
        the raw `37`/`38`.
        """
        debit_move = self._entry(45.0, debit_side=True)
        credit_move = self._entry(45.0, debit_side=False)
        (self._receivable_line(debit_move)
         + self._receivable_line(credit_move)).reconcile()

        exported = self._receivable_line(debit_move).export_data(
            ["matching_number", "matching_label"])["datas"][0]
        token, label = exported
        self.assertTrue(token, "the raw token is still exportable")
        self.assertIn("Matched", label)
        self.assertIn(credit_move.name, label)

    def test_the_status_can_be_grouped_and_searched(self):
        """What storing the field buys. If it were non-stored, both would fail."""
        self._entry(150.0)  # an open receivable

        groups = self.env["account.move.line"]._read_group(
            [("company_id", "=", self.company.id)],
            groupby=["matching_status"], aggregates=["__count"])
        by_status = dict(groups)
        self.assertIn("open", by_status)
        self.assertIn("not_reconcilable", by_status)

        found = self.env["account.move.line"].search([
            ("matching_status", "=", "open"),
            ("account_id", "=", self.receivable.id),
        ])
        self.assertTrue(found)
        self.assertTrue(all(aml.amount_residual for aml in found),
                        "every 'open' line must actually have a residual")

    def test_clicking_a_matched_cell_opens_its_counterparts(self):
        """The widget calls core's `open_reconcile_view`; assert it resolves here.

        Asserting the server side rather than the click: the JS test covers which
        cells are clickable, this covers that the thing they call returns a usable
        action containing the counterpart.
        """
        debit_move = self._entry(70.0, debit_side=True)
        credit_move = self._entry(70.0, debit_side=False)
        lines = self._receivable_line(debit_move) + self._receivable_line(credit_move)
        lines.reconcile()

        action = self._receivable_line(debit_move).open_reconcile_view()
        self.assertEqual(action["res_model"], "account.move.line")
        opened = self.env["account.move.line"].search(action["domain"])
        self.assertIn(self._receivable_line(credit_move), opened,
                      "the action must open the line this one was matched against")

    def test_the_javascript_knows_every_state(self):
        """The states are defined in Python; their colours live in JavaScript.

        Nothing connects the two files, so adding a sixth state to the Selection
        without adding it to `STATE_STYLE` would render it unstyled and
        un-clickable, and no test would notice. This reads the JS and compares.
        Same shape as the Python-JS contract test in
        `nepali_calendar_core/tests/test_conversion_contract.py`, and for the same
        reason: two sources of truth need something asserting they agree.
        """
        widget = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static", "src", "matching_cell.js")
        with open(widget, encoding="utf-8") as handle:
            source = handle.read()

        # Sliced rather than matched with a brace-heavy regex: the keys are what
        # matter, and a regex spanning `{...}` here is harder to read than the
        # thing it parses.
        marker = "export const STATE_STYLE = {"
        self.assertIn(marker, source, "STATE_STYLE not found in matching_cell.js")
        block = source.split(marker, 1)[1].split("};", 1)[0]
        in_js = set(re.findall(r"^\s*(\w+):", block, re.M))

        in_python = {
            value for value, _label
            in self.env["account.move.line"]._fields["matching_status"].selection
        }
        self.assertEqual(
            in_js, in_python,
            f"matching_cell.js styles {sorted(in_js)} but the Selection defines "
            f"{sorted(in_python)}; a state with no style renders unstyled")

    def test_the_raw_matching_number_column_is_still_in_the_view(self):
        """Demoting it must not remove it.

        `account.view_account_move_line_filter` builds domains on
        `matching_number` (account_move_views.xml:343-348) and offers a group-by
        on it (:381). Dropping the field from the arch would break both, and the
        breakage would show up as a filter that silently returns everything.
        """
        arch = self.env.ref("account.view_move_line_tree").get_combined_arch()
        self.assertIn('name="matching_number"', arch)
        self.assertIn('name="matching_label"', arch)
        self.assertIn('widget="account_matching"', arch)
        self.assertIn('name="matching_status"', arch)
