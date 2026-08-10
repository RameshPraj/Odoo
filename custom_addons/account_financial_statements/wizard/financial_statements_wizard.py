# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class FinancialStatementsWizard(models.TransientModel):
    _name = 'account.financial.statements.wizard'
    _description = 'Balance Sheet / Profit and Loss'

    # Which statement to print. Defaulted from the context so that one menu item
    # per statement can open this same wizard pre-aimed, instead of offering a
    # row of three buttons and making the user pick again.
    report_type = fields.Selection(
        [('balance_sheet', 'Balance Sheet'),
         ('profit_loss', 'Profit and Loss'),
         ('cash_flow', 'Cash Flow Statement')],
        required=True, default='balance_sheet',
    )
    # True when the caller already chose the statement, so the selector is
    # redundant and is hidden. Purely presentational.
    report_type_locked = fields.Boolean(default=False)

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        required=True, default=lambda self: self._default_date_from(),
        help="Start of the period. Ignored by the Balance Sheet, which is "
             "always cumulative up to the end date.",
    )
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    target_move = fields.Selection(
        [('posted', 'Posted entries only'), ('all', 'Posted and draft entries')],
        required=True, default='posted',
    )
    hide_zero = fields.Boolean(string='Hide zero-balance accounts', default=True)

    def _default_date_from(self):
        """First day of the current fiscal year, which on a Nepali company is
        Shrawan 1 rather than 1 January."""
        company = self.env.company
        return company.compute_fiscalyear_dates(fields.Date.context_today(self))['date_from']

    def _check(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_("The start date must not be after the end date."))

    def _data(self):
        return {'wizard_id': self.id}

    def action_print(self):
        """Print whichever statement report_type names."""
        self.ensure_one()
        return {
            'balance_sheet': self.action_balance_sheet,
            'profit_loss': self.action_profit_loss,
            'cash_flow': self.action_cash_flow,
        }[self.report_type]()

    def action_balance_sheet(self):
        self._check()
        return self.env.ref(
            'account_financial_statements.action_report_balance_sheet'
        ).report_action(self, data=self._data())

    def action_profit_loss(self):
        self._check()
        return self.env.ref(
            'account_financial_statements.action_report_profit_loss'
        ).report_action(self, data=self._data())

    def action_cash_flow(self):
        self._check()
        return self.env.ref(
            'account_financial_statements.action_report_cash_flow'
        ).report_action(self, data=self._data())
