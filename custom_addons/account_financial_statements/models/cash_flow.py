# -*- coding: utf-8 -*-
"""Cash Flow Statement.

Method: cash-based classification. Rather than deriving cash movement indirectly
from profit, this walks every journal item that touched a cash account in the
period, then classifies each one by the account types of the *counterpart* lines
in the same journal entry:

    counterpart is receivable / payable / income / expense / current  -> Operating
    counterpart is fixed / non-current asset                          -> Investing
    counterpart is equity / non-current liability                     -> Financing

The advantage is that the statement is self-proving: the sum of all classified
movements must equal closing cash minus opening cash. A test asserts exactly
that, so a classification bug cannot pass silently.
"""
from odoo import api, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

CASH_TYPES = ('asset_cash',)

OPERATING = (
    'asset_receivable', 'liability_payable', 'income', 'income_other',
    'expense', 'expense_direct_cost', 'expense_depreciation',
    'asset_current', 'asset_prepayments', 'liability_current',
    'liability_credit_card',
)
INVESTING = ('asset_fixed', 'asset_non_current')
FINANCING = ('equity', 'equity_unaffected', 'liability_non_current')

SECTION_LABELS = {
    'operating': _lt("Cash flows from operating activities"),
    'investing': _lt("Cash flows from investing activities"),
    'financing': _lt("Cash flows from financing activities"),
    'unclassified': _lt("Unclassified movements"),
}


class ReportCashFlow(models.AbstractModel):
    # Must match action_report_cash_flow's report_name: Odoo derives this model
    # name as 'report.%s' % report_name (ir_actions_report.py:1121-1123), and
    # the name is kept short because the derived table name has a 63-character
    # limit. See the note in models/financial_statements.py.
    _name = 'report.account_financial_statements.cash_flow'
    _inherit = 'account.financial.statements.common'
    _description = 'Cash Flow Statement'

    # ------------------------------------------------------------------
    @api.model
    def _cash_accounts(self, wizard):
        return self.env['account.account'].search([
            ('account_type', 'in', list(CASH_TYPES)),
            ('company_ids', 'in', wizard.company_id.id),
        ])

    @api.model
    def _cash_balance_at(self, wizard, date_to):
        """Cumulative cash balance up to and including ``date_to``."""
        domain = [
            ('company_id', '=', wizard.company_id.id),
            ('account_id.account_type', 'in', list(CASH_TYPES)),
            ('date', '<=', date_to),
        ]
        if wizard.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        else:
            domain.append(('parent_state', 'in', ('posted', 'draft')))
        groups = self.env['account.move.line']._read_group(
            domain, groupby=[], aggregates=['balance:sum'])
        return groups[0][0] or 0.0 if groups else 0.0

    @api.model
    def _classify(self, account_type):
        if account_type in OPERATING:
            return 'operating'
        if account_type in INVESTING:
            return 'investing'
        if account_type in FINANCING:
            return 'financing'
        return 'unclassified'

    @api.model
    def _movements(self, wizard):
        """Classified cash movements for the period.

        For every cash line in the period, the counterpart lines of the same move
        decide the section. Where a move has several counterparts the cash amount
        is apportioned across them in proportion to their absolute balances, so
        nothing is double counted and the totals still tie.
        """
        AML = self.env['account.move.line']
        state_domain = ([('parent_state', '=', 'posted')]
                        if wizard.target_move == 'posted'
                        else [('parent_state', 'in', ('posted', 'draft'))])

        cash_lines = AML.search([
            ('company_id', '=', wizard.company_id.id),
            ('account_id.account_type', 'in', list(CASH_TYPES)),
            ('date', '>=', wizard.date_from),
            ('date', '<=', wizard.date_to),
        ] + state_domain)

        sections = {k: {} for k in ('operating', 'investing', 'financing', 'unclassified')}

        for move in cash_lines.mapped('move_id'):
            move_cash = move.line_ids.filtered(
                lambda l: l.account_id.account_type in CASH_TYPES and l in cash_lines)
            cash_amount = sum(move_cash.mapped('balance'))
            if wizard.company_id.currency_id.is_zero(cash_amount):
                continue

            counterparts = move.line_ids - move_cash
            weight_total = sum(abs(l.balance) for l in counterparts)

            if not counterparts or wizard.company_id.currency_id.is_zero(weight_total):
                bucket = sections['unclassified'].setdefault(
                    (0, str(SECTION_LABELS['unclassified'])), 0.0)
                sections['unclassified'][(0, str(SECTION_LABELS['unclassified']))] = \
                    bucket + cash_amount
                continue

            for line in counterparts:
                share = cash_amount * (abs(line.balance) / weight_total)
                section = self._classify(line.account_id.account_type)
                key = (line.account_id.id, f"{line.account_id.code} {line.account_id.name}")
                sections[section][key] = sections[section].get(key, 0.0) + share

        out = {}
        for name, buckets in sections.items():
            lines = [{'label': label, 'amount': amount}
                     for (_aid, label), amount in sorted(buckets.items(), key=lambda kv: kv[0][1])
                     if not (wizard.hide_zero
                             and wizard.company_id.currency_id.is_zero(amount))]
            out[name] = {
                'label': str(SECTION_LABELS[name]),
                'lines': lines,
                'total': sum(line['amount'] for line in lines),
            }
        return out

    # ------------------------------------------------------------------
    @api.model
    def _get_report_values(self, docids, data=None):
        import datetime  # noqa: PLC0415
        wizard = self._wizard_from(docids, data)

        opening = self._cash_balance_at(
            wizard, wizard.date_from - datetime.timedelta(days=1))
        closing = self._cash_balance_at(wizard, wizard.date_to)
        sections = self._movements(wizard)

        movement_total = sum(s['total'] for s in sections.values())
        net_change = closing - opening
        difference = movement_total - net_change

        return {
            'doc_model': 'account.financial.statements.wizard',
            'docs': wizard,
            'wizard': wizard,
            'sections': [sections['operating'], sections['investing'],
                         sections['financing'], sections['unclassified']],
            'opening': opening,
            'closing': closing,
            'net_change': net_change,
            'movement_total': movement_total,
            'difference': difference,
            'reconciled': wizard.company_id.currency_id.is_zero(difference),
        }
