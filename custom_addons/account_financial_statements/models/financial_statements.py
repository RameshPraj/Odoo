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
    def _state_domain(self, wizard):
        """The posted/draft leaf, in exactly one place.

        Three copies of this rule existed -- here, in ``_cash_balance_at`` and in
        ``_movements`` -- and they had already drifted: the cash-flow ones also
        omitted the ``off_balance`` exclusion. Since a drill-down now claims to
        show "the lines behind this figure", any such divergence stops being a
        cosmetic inconsistency and becomes a wrong answer.
        """
        if wizard.target_move == 'posted':
            return [('parent_state', '=', 'posted')]
        return [('parent_state', 'in', ('posted', 'draft'))]

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
        return domain + self._state_domain(wizard)

    @api.model
    def _balances_by_account(self, wizard, account_types, date_from=None):
        """Return ``[{account, balance, domain}, ...]`` summed per account.

        ``domain`` is the exact expression whose ``balance`` sum produced that
        row's figure, returned rather than reconstructed later. That is the whole
        point: a drill-down that disagrees with the figure it came from is worse
        than no drill-down, because it turns a number you would have trusted into
        one you now cannot. Sharing one expression makes the two agree
        structurally instead of by a convention someone has to remember -- and the
        convention is easy to get wrong, since ``date_from`` is ``None`` for the
        balance sheet, the fiscal-year start for the period result, and
        ``wizard.date_from`` for the P&L.
        """
        base = self._move_line_domain(wizard, date_from)
        groups = self.env['account.move.line']._read_group(
            base + [('account_id.account_type', 'in', list(account_types))],
            groupby=['account_id'], aggregates=['balance:sum'],
        )
        rows = []
        for account, balance in groups:
            if wizard.company_id.currency_id.is_zero(balance) and wizard.hide_zero:
                continue
            rows.append({
                'account': account,
                'balance': balance,
                # Pinning account_id makes the account_type leaf redundant, so it
                # is left out: a narrower domain is easier to read in the UI.
                'domain': base + [('account_id', '=', account.id)],
            })
        return sorted(rows, key=lambda r: r['account'].code or '')

    @api.model
    def _section(self, wizard, account_types, sign, date_from=None):
        """Build one presentational section.

        :param sign: +1 keeps Odoo's debit-positive balance (assets, expenses),
                     -1 flips it so credit balances read positive
                     (liabilities, equity, income).
        """
        base = self._move_line_domain(wizard, date_from)
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
                'account_id': r['account'].id,
                'domain': r['domain'],
                # The sign has to travel with the figure. Without it a
                # liabilities drill-down opens a list whose Total Balance is the
                # negation of the number that was clicked, which reads as a bug
                # in the report rather than as Odoo's debit-positive convention.
                'sign': sign,
            } for r in rows]
            subtotal = sum(line['amount'] for line in lines)
            blocks.append({
                'label': TYPE_LABELS.get(atype, atype),
                'lines': lines,
                'subtotal': subtotal,
                'domain': base + [('account_id.account_type', '=', atype)],
                'sign': sign,
            })
            total += subtotal
        # Dropping zero rows and empty blocks above does not affect these sums, so
        # the section domain still ties to `total`.
        return {
            'blocks': blocks,
            'total': total,
            'domain': base + [('account_id.account_type', 'in', list(account_types))],
            'sign': sign,
        }

    @api.model
    def _period_result(self, wizard, date_from):
        """Net profit for a period: income (credit) minus expenses (debit)."""
        income = self._section(wizard, INCOME_TYPES, -1, date_from)['total']
        expense = self._section(wizard, EXPENSE_TYPES, +1, date_from)['total']
        return income - expense

    @api.model
    def _period_result_domain(self, wizard, date_from):
        """Lines behind the current-period result.

        Sign is -1, and the arithmetic is worth spelling out because it is not
        obvious: the figure is ``(-sum income) - (+sum expense)``, which
        rearranges to ``-(sum income + sum expense)``. So the ``balance`` sum over
        this one domain is the negation of the printed result, and presenting it
        with any other sign would put a drill-down on screen that contradicts the
        line it hangs off.
        """
        return self._move_line_domain(wizard, date_from) + [
            ('account_id.account_type', 'in', list(INCOME_TYPES + EXPENSE_TYPES)),
        ]

    # ------------------------------------------------------------------
    @api.model
    def _anomalies(self, wizard):
        """Reasons a figure on this statement might not be trustworthy.

        Returned as data and rendered by QWeb rather than assembled in JavaScript,
        so the warnings reach the PDF as well as the screen. A caveat that is
        visible while you read but absent from the copy you file is worse than no
        caveat, because the filed copy is the one someone relies on later.

        Every entry carries a domain, so each warning is itself a drill-down: the
        point is not to say "something is wrong" but to open the offending records.
        """
        AML = self.env['account.move.line']
        currency = wizard.company_id.currency_id
        found = []

        # Draft entries are being counted, so every figure is provisional.
        if wizard.target_move != 'posted':
            draft = [
                ('company_id', '=', wizard.company_id.id),
                ('date', '<=', wizard.date_to),
                ('parent_state', '=', 'draft'),
                ('account_id.account_type', '!=', 'off_balance'),
            ]
            count = AML.search_count(draft)
            if count:
                found.append({
                    'level': 'warning',
                    'message': _(
                        "%(count)s draft journal item(s) are included because "
                        "Target Moves is set to All Entries. Every figure below is "
                        "provisional.", count=count,
                    ),
                    'domain': draft,
                })

        # Off-balance amounts. _move_line_domain excludes account_type
        # 'off_balance' by design, so these are invisible on the statement -- which
        # means they can silently be the explanation for a figure that looks short.
        off_balance = [
            ('company_id', '=', wizard.company_id.id),
            ('date', '<=', wizard.date_to),
            ('account_id.account_type', '=', 'off_balance'),
        ] + self._state_domain(wizard)
        if AML.search_count(off_balance):
            found.append({
                'level': 'info',
                'message': _(
                    "There are amounts in off-balance-sheet accounts. They are "
                    "deliberately excluded from this statement, so they will not "
                    "appear in any figure above."
                ),
                'domain': off_balance,
            })

        # Journal entries whose own debits and credits do not agree. Computed
        # WITHOUT the off_balance exclusion on purpose: a move with one
        # off-balance line is balanced in reality, and filtering that line out
        # first would report it as broken.
        every_line = [
            ('company_id', '=', wizard.company_id.id),
            ('date', '<=', wizard.date_to),
        ] + self._state_domain(wizard)
        unbalanced = [
            move.id
            for move, balance in AML._read_group(
                every_line, groupby=['move_id'], aggregates=['balance:sum'])
            if move and not currency.is_zero(balance)
        ]
        if unbalanced:
            found.append({
                'level': 'danger',
                'message': _(
                    "%(count)s journal entr(y/ies) do not balance: their debits and "
                    "credits differ. Until they are corrected the statement cannot "
                    "be relied on.", count=len(unbalanced),
                ),
                'domain': [('move_id', 'in', unbalanced)],
            })

        return found


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

        anomalies = self._anomalies(wizard)
        if not wizard.company_id.currency_id.is_zero(difference):
            # The sheet not balancing is the most consequential thing this report
            # can tell you, so it leads the list. The domain is every line the
            # statement drew on, which is where the discrepancy has to be.
            anomalies.insert(0, {
                'level': 'danger',
                'message': _(
                    "Assets do not equal liabilities plus equity; the difference is "
                    "%(difference)s. Something below is wrong, or an entry is "
                    "missing.", difference=difference,
                ),
                'domain': self._move_line_domain(wizard),
            })

        return {
            'doc_model': 'account.financial.statements.wizard',
            'docs': wizard,
            'wizard': wizard,
            'assets': assets,
            'liabilities': liabilities,
            'equity': equity,
            'result': result,
            'result_domain': self._period_result_domain(wizard, fy['date_from']),
            'result_sign': -1,
            'anomalies': anomalies,
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
            # Net profit spans income and every expense type, so its drill-down is
            # the union -- and like the balance sheet's result line, the balance
            # sum over it is the negation of the figure.
            'net_domain': self._period_result_domain(wizard, wizard.date_from),
            'net_sign': -1,
            'anomalies': self._anomalies(wizard),
        }
