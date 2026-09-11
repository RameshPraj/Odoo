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
from odoo import _, api, models
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
    # `_cash_accounts` used to live here: it searched account.account by
    # CASH_TYPES and was never called from anywhere in the repository. Removed
    # rather than left as a trap for whoever tries to use it -- it also filtered
    # on `company_ids`, where every other query in this module uses
    # account.move.line's `company_id`.

    @api.model
    def _cash_balance_domain(self, wizard, date_to):
        """Lines making up the cash balance as at ``date_to``.

        Separate from `_move_line_domain` because that one is pinned to
        `wizard.date_to`, whereas the opening balance needs the day before
        `date_from`. The posted/draft rule comes from `_state_domain` so this is no
        longer a third private copy of it.

        No `off_balance` exclusion is needed, unlike `_move_line_domain`:
        `account_type` is a single Selection value, so `in CASH_TYPES` already
        rules `off_balance` out.
        """
        return [
            ('company_id', '=', wizard.company_id.id),
            ('account_id.account_type', 'in', list(CASH_TYPES)),
            ('date', '<=', date_to),
        ] + self._state_domain(wizard)

    @api.model
    def _cash_balance_at(self, wizard, date_to):
        """Cumulative cash balance up to and including ``date_to``."""
        groups = self.env['account.move.line']._read_group(
            self._cash_balance_domain(wizard, date_to),
            groupby=[], aggregates=['balance:sum'])
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

        cash_lines = AML.search([
            ('company_id', '=', wizard.company_id.id),
            ('account_id.account_type', 'in', list(CASH_TYPES)),
            ('date', '>=', wizard.date_from),
            ('date', '<=', wizard.date_to),
        ] + self._state_domain(wizard))

        sections = {k: {} for k in ('operating', 'investing', 'financing', 'unclassified')}
        # Which move lines fed each bucket. Cash-flow figures are apportioned
        # shares (see below), so unlike every other statement here they cannot be
        # recovered from a domain -- the ids have to be collected while the
        # apportioning happens or they are gone.
        contributors = {k: {} for k in sections}

        for move in cash_lines.mapped('move_id'):
            move_cash = move.line_ids.filtered(
                lambda aml: aml.account_id.account_type in CASH_TYPES
                and aml in cash_lines)
            cash_amount = sum(move_cash.mapped('balance'))
            if wizard.company_id.currency_id.is_zero(cash_amount):
                continue

            counterparts = move.line_ids - move_cash
            weight_total = sum(abs(aml.balance) for aml in counterparts)

            if not counterparts or wizard.company_id.currency_id.is_zero(weight_total):
                key = (0, str(SECTION_LABELS['unclassified']))
                sections['unclassified'][key] = \
                    sections['unclassified'].get(key, 0.0) + cash_amount
                # With no usable counterpart the cash lines themselves are the only
                # thing to show.
                contributors['unclassified'].setdefault(key, set()).update(move_cash.ids)
                continue

            for line in counterparts:
                share = cash_amount * (abs(line.balance) / weight_total)
                section = self._classify(line.account_id.account_type)
                key = (line.account_id.id, f"{line.account_id.code} {line.account_id.name}")
                sections[section][key] = sections[section].get(key, 0.0) + share
                contributors[section].setdefault(key, set()).add(line.id)

        out = {}
        for name, buckets in sections.items():
            lines = []
            for key, amount in sorted(buckets.items(), key=lambda kv: kv[0][1]):
                if wizard.hide_zero and wizard.company_id.currency_id.is_zero(amount):
                    continue
                ids = sorted(contributors[name].get(key, ()))
                lines.append({
                    'label': key[1],
                    'amount': amount,
                    'account_id': key[0] or False,
                    # Deliberately NOT presented as "the lines behind this figure".
                    # `amount` is a pro-rata share of a cash movement, not the sum
                    # of any field on these records, so their balance total will
                    # not equal it. Claiming otherwise would be the one thing this
                    # feature must never do: show a drill-down that silently
                    # contradicts the number above it.
                    'contributor_ids': ids,
                    'contributor_domain': [('id', 'in', ids)] if ids else False,
                })
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

        anomalies = self._anomalies(wizard)
        if not wizard.company_id.currency_id.is_zero(difference):
            anomalies.insert(0, {
                'level': 'danger',
                'message': _(
                    "Classified movements do not tie to the change in cash; the "
                    "difference is %(difference)s. A movement has been classified "
                    "into the wrong section, or missed.", difference=difference,
                ),
                'domain': self._cash_balance_domain(wizard, wizard.date_to)
                + [('date', '>=', wizard.date_from)],
            })
        if sections['unclassified']['lines']:
            anomalies.append({
                'level': 'warning',
                'message': _(
                    "Some movements could not be classified as operating, investing "
                    "or financing. They are still counted, so the statement ties, "
                    "but they are not attributed to an activity."
                ),
                'domain': [('id', 'in', [
                    lid
                    for line in sections['unclassified']['lines']
                    for lid in line['contributor_ids']
                ])],
            })

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
            # Opening and closing cash ARE plain sums, so unlike the movement
            # lines these two drill down exactly.
            'opening_domain': self._cash_balance_domain(
                wizard, wizard.date_from - datetime.timedelta(days=1)),
            'closing_domain': self._cash_balance_domain(wizard, wizard.date_to),
            'anomalies': anomalies,
        }
