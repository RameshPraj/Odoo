# -*- coding: utf-8 -*-
"""A mistyped Journal Items Domain says so, instead of raising (SEC-10).

`general_ledger_wizard.py:93-95` parses a user-editable `Char` into a domain:

    def _get_account_move_lines_domain(self):
        domain = literal_eval(self.domain) if self.domain else []

**The register's prescribed fix is not applied here, and deliberately.** It reads
"`literal_eval` on a user-editable domain; `safe_eval` is house style", which
reads as though `literal_eval` were the weaker of the two. It is the stronger
one: it evaluates literals only and resolves no names at all, whereas `safe_eval`
exists precisely to *permit* a controlled set of names and calls. Measured
against this wizard rather than argued:

    "[('x','=',1)"      -> SyntaxError: '[' was never closed
    "not a domain"      -> SyntaxError: invalid syntax
    "__import__('os')"  -> ValueError: malformed node or string

The third is the one that matters. `literal_eval` already refuses code, so
swapping to `safe_eval` would widen what this field accepts while fixing nothing.

What the measurement did show is the real defect: every one of those is an
**unhandled exception**. A user who mistypes a domain gets a raw SyntaxError
traceback rather than a sentence telling them which field is wrong, which is the
opposite of how every other refusal in this codebase behaves.

So the fix is to translate, not to substitute. `super()` is called and its
exception re-raised as a `UserError`; **no vendored code is copied**, which
matters because `account_financial_report` is AGPL-3 and this module is LGPL-3
(see the note in `controllers/main.py` and finding LIC-1).
"""
from odoo import _, models
from odoo.exceptions import UserError


class GeneralLedgerReportWizard(models.TransientModel):
    _inherit = "general.ledger.report.wizard"

    def _get_account_move_lines_domain(self):
        try:
            return super()._get_account_move_lines_domain()
        except (SyntaxError, ValueError) as exc:
            raise UserError(_(
                "The Journal Items Domain is not a valid domain:\n\n%(problem)s\n\n"
                "It must be a plain list of tuples, for example:\n"
                "    [('partner_id', '!=', False)]\n\n"
                "Only literal values are accepted here -- no names, functions or "
                "expressions.",
                problem=exc,
            )) from exc
