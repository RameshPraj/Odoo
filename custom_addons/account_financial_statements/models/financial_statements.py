# -*- coding: utf-8 -*-
"""Balance Sheet and Profit & Loss computation.

Community Odoo ships the account.report schema without its renderer, and OCA's
account_financial_report covers ledgers rather than statements, so these two are
built here directly over account.move.line.

Design note: sections are keyed on ``account.account.account_type``, not on code
prefixes. Account codes are a chart convention and will change when the chart is
reviewed; account types are Odoo semantics and will not.

Sign convention inside Odoo: ``balance`` is debit-positive. Assets and expenses
therefore carry positive balances, while liabilities, equity and income carry
negative ones. Everything below is normalised so that each figure is presented
the way an accountant expects to read it.
"""
from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools.translate import LazyTranslate

# Module-level constants must use lazy translation: plain _() at import time has
# no language context and Odoo warns "no translation language detected".
_lt = LazyTranslate(__name__)

ASSET_TYPES = (
    'asset_receivable', 'asset_cash', 'asset_current',
    'asset_non_current', 'asset_prepayments', 'asset_fixed',
)
LIABILITY_TYPES = (
    'liability_payable', 'liability_credit_card',
    'liability_current', 'liability_non_current',
)
EQUITY_TYPES = ('equity', 'equity_unaffected')
INCOME_TYPES = ('income', 'income_other')
EXPENSE_TYPES = ('expense', 'expense_direct_cost', 'expense_depreciation')

TYPE_LABELS = {
    'asset_receivable': _lt("Receivables"),
    'asset_cash': _lt("Bank and Cash"),
    'asset_current': _lt("Current Assets"),
    'asset_non_current': _lt("Non-current Assets"),
    'asset_prepayments': _lt("Prepayments"),
    'asset_fixed': _lt("Fixed Assets"),
    'liability_payable': _lt("Payables"),
    'liability_credit_card': _lt("Credit Cards"),
    'liability_current': _lt("Current Liabilities"),
    'liability_non_current': _lt("Non-current Liabilities"),
    'equity': _lt("Equity"),
    'equity_unaffected': _lt("Retained Earnings"),
    'income': _lt("Operating Revenue"),
    'income_other': _lt("Other Income"),
    'expense_direct_cost': _lt("Cost of Sales"),
    'expense': _lt("Operating Expenses"),
    'expense_depreciation': _lt("Depreciation"),
}


class FinancialStatementsCommon(models.AbstractModel):
    _name = 'account.financial.statements.common'
    _description = 'Financial statements computation'

    @api.model
    def _wizard_from(self, docids, data):
        """The wizard this report is rendering, from either route.

        The wizard's buttons pass ``data={'wizard_id': id}`` through
        ``report_action``, but a report opened directly by URL --
        ``/report/html/<report_name>/<id>`` -- arrives with empty ``data`` and the
        ids in ``docids``. Reading ``data['wizard_id']`` unconditionally raises
        KeyError on that second route, which is also the route the error page's
        own retry link uses.
        """
        wizard_id = (data or {}).get('wizard_id') or docids
        wizard = self.env['account.financial.statements.wizard'].browse(wizard_id)
        if not wizard.exists():
            raise UserError(_(
                "This report must be opened from the Financial Statements wizard, "
                "which supplies the reporting period and company."
            ))
        return wizard.ensure_one()

    # ------------------------------------------------------------------
    @api.model
    def _move_line_domain(self, wizard, date_from=None):
        """Base domain. ``date_from=None`` means 'since inception' (balance sheet)."""
        domain = [
            ('company_id', '=', wizard.company_id.id),
            ('date', '<=', wizard.date_to),
            ('account_id.account_type', '!=', 'off_balance'),
        ]
        if date_from:
            domain.append(('date', '>=', date_from))
        if wizard.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        else:
            domain.append(('parent_state', 'in', ('posted', 'draft')))
        return domain

    @api.model
    def _balances_by_account(self, wizard, account_types, date_from=None):
        """Return ``[{account, balance}, ...]`` summed per account, zero rows dropped."""
        domain = self._move_line_domain(wizard, date_from) + [
            ('account_id.account_type', 'in', list(account_types)),
        ]
        groups = self.env['account.move.line']._read_group(
            domain, groupby=['account_id'], aggregates=['balance:sum'],
        )
        rows = []
        for account, balance in groups:
            if wizard.company_id.currency_id.is_zero(balance) and wizard.hide_zero:
                continue
            rows.append({'account': account, 'balance': balance})
        return sorted(rows, key=lambda r: r['account'].code or '')

    @api.model
    def _section(self, wizard, account_types, sign, date_from=None):
        """Build one presentational section.

        :param sign: +1 keeps Odoo's debit-positive balance (assets, expenses),
                     -1 flips it so credit balances read positive
                     (liabilities, equity, income).
        """
        blocks = []
        total = 0.0
        for atype in account_types:
            rows = self._balances_by_account(wizard, (atype,), date_from)
            if not rows:
                continue
            lines = [{
                'code': r['account'].code,
                'name': r['account'].name,
                'amount': sign * r['balance'],
            } for r in rows]
            subtotal = sum(line['amount'] for line in lines)
            blocks.append({
                'label': TYPE_LABELS.get(atype, atype),
                'lines': lines,
                'subtotal': subtotal,
            })
            total += subtotal
        return {'blocks': blocks, 'total': total}

    @api.model
    def _period_result(self, wizard, date_from):
        """Net profit for a period: income (credit) minus expenses (debit)."""
        income = self._section(wizard, INCOME_TYPES, -1, date_from)['total']
        expense = self._section(wizard, EXPENSE_TYPES, +1, date_from)['total']
        return income - expense


class ReportBalanceSheet(models.AbstractModel):
    # The name is NOT free: Odoo resolves the values model mechanically as
    # 'report.%s' % report_name (ir_actions_report.py:1121-1123), so this must
    # equal the report action's report_name -- and therefore the template's
    # xml-id. When it did not, _get_report_values never ran and every statement
    # died with KeyError: 'wizard'.
    #
    # The names are short on purpose. Odoo derives a table name from _name even
    # for an AbstractModel and validates its length, and
    # 'report_account_financial_statements_report_balance_sheet_document' is 65
    # characters -- past PostgreSQL's 63-character identifier limit. So the
    # template is named `balance_sheet`, not `report_balance_sheet_document`.
    _name = 'report.account_financial_statements.balance_sheet'
    _inherit = 'account.financial.statements.common'
    _description = 'Balance Sheet'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self._wizard_from(docids, data)

        # A balance sheet is cumulative: no lower date bound.
        assets = self._section(wizard, ASSET_TYPES, +1)
        liabilities = self._section(wizard, LIABILITY_TYPES, -1)
        equity = self._section(wizard, EQUITY_TYPES, -1)

        # Current-period result is not posted to equity; without it the sheet
        # will not balance.
        fy = wizard.company_id.compute_fiscalyear_dates(wizard.date_to)
        result = self._period_result(wizard, fy['date_from'])

        total_equity = equity['total'] + result
        difference = assets['total'] - (liabilities['total'] + total_equity)

        return {
            'doc_model': 'account.financial.statements.wizard',
            'docs': wizard,
            'wizard': wizard,
            'assets': assets,
            'liabilities': liabilities,
            'equity': equity,
            'result': result,
            'result_label': _("Current Period Result"),
            'total_equity': total_equity,
            'total_liab_equity': liabilities['total'] + total_equity,
            'difference': difference,
            'balanced': wizard.company_id.currency_id.is_zero(difference),
            'fy_from': fy['date_from'],
            'fy_to': fy['date_to'],
        }


class ReportProfitLoss(models.AbstractModel):
    # Must match action_report_profit_loss's report_name -- see the note above.
    _name = 'report.account_financial_statements.profit_loss'
    _inherit = 'account.financial.statements.common'
    _description = 'Profit and Loss'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self._wizard_from(docids, data)

        income = self._section(wizard, INCOME_TYPES, -1, wizard.date_from)
        cost_of_sales = self._section(wizard, ('expense_direct_cost',), +1, wizard.date_from)
        expenses = self._section(wizard, ('expense', 'expense_depreciation'), +1, wizard.date_from)

        gross = income['total'] - cost_of_sales['total']
        net = gross - expenses['total']

        return {
            'doc_model': 'account.financial.statements.wizard',
            'docs': wizard,
            'wizard': wizard,
            'income': income,
            'cost_of_sales': cost_of_sales,
            'expenses': expenses,
            'gross': gross,
            'net': net,
        }
