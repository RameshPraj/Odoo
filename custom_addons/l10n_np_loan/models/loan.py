# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Loan register with an amortisation schedule that posts to the ledger.

Enterprise's `account_loans` (OEEL-1) is not usable here, so this is written from
scratch. It is deliberately named `l10n_np_loan` rather than `account_loan` so
that OCA's module of that name can still be installed alongside it.

Every number a lender sets -- rate, term, frequency, method -- is a field on the
loan record, never a constant in this file. Two loans from two banks on two rates
are just two records.
"""
from dateutil.relativedelta import relativedelta
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

# Instalments per year, by payment frequency.
PERIODS_PER_YEAR = {
    'monthly': 12,
    'quarterly': 4,
    'semiannual': 2,
    'annual': 1,
}


class Loan(models.Model):
    _name = 'l10n_np.loan'
    _description = 'Loan'
    _inherit = ['mail.thread']
    _order = 'date_start desc, id desc'

    name = fields.Char(
        required=True, tracking=True,
        help="How this loan is referred to internally, e.g. 'NIC Asia term loan 2083'.",
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        # Indexed because SEC-2's record rule filters every query on it (SCH-1).
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', required=True,
        default=lambda self: self.env.company.currency_id,
    )
    partner_id = fields.Many2one(
        'res.partner', string="Lender", required=True, tracking=True, index=True,
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('open', 'Running'),
         ('closed', 'Closed'), ('cancel', 'Cancelled')],
        default='draft', required=True, tracking=True,
    )

    # -- terms ---------------------------------------------------------------
    principal = fields.Monetary(
        required=True, tracking=True,
        help="Amount borrowed.",
    )
    rate = fields.Float(
        string="Annual rate (%)", digits=(16, 4), required=True, tracking=True,
        help="Nominal annual interest rate. Divided by the number of "
             "instalments per year to give the rate applied each period.",
    )
    date_start = fields.Date(
        required=True, tracking=True, default=fields.Date.context_today,
        help="Drawdown date. The first instalment falls one period after it.",
    )
    term = fields.Integer(
        string="Instalments", required=True, default=12, tracking=True,
        help="Total number of instalments.",
    )
    frequency = fields.Selection(
        [('monthly', 'Monthly'), ('quarterly', 'Quarterly'),
         ('semiannual', 'Half-yearly'), ('annual', 'Yearly')],
        default='monthly', required=True, tracking=True,
    )
    method = fields.Selection(
        [('emi', 'Equal instalment (EMI)'),
         ('equal_principal', 'Equal principal'),
         ('interest_only', 'Interest only, principal at maturity')],
        default='emi', required=True, tracking=True,
        help="Equal instalment: every payment is the same, the split between "
             "principal and interest shifts over time.\n"
             "Equal principal: principal repaid in equal slices, so payments "
             "fall over time.\n"
             "Interest only: interest each period, whole principal at maturity.",
    )

    # -- accounts ------------------------------------------------------------
    journal_id = fields.Many2one(
        # No `string=`: Odoo derives "Journal" from the field name, and repeating
        # it means a future rename silently keeps the old label.
        'account.journal', required=True,
        domain="[('company_id', '=', company_id)]",
        check_company=True,
    )
    loan_account_id = fields.Many2one(
        'account.account', string="Loan account", required=True,
        check_company=True,
        domain="[('account_type', 'in', ('liability_current', 'liability_non_current'))]",
        help="Liability account carrying the outstanding principal.",
    )
    interest_account_id = fields.Many2one(
        'account.account', string="Interest expense", required=True,
        check_company=True,
        domain="[('account_type', '=', 'expense')]",
    )
    payment_account_id = fields.Many2one(
        'account.account', string="Bank / cash account", required=True,
        check_company=True,
        domain="[('account_type', 'in', ('asset_cash', 'asset_current', 'liability_payable'))]",
        help="The account money is drawn into and instalments are paid from.",
    )

    line_ids = fields.One2many('l10n_np.loan.line', 'loan_id', string="Schedule")
    disbursement_move_id = fields.Many2one(
        'account.move', string="Drawdown entry", readonly=True, copy=False,
    )

    # -- totals --------------------------------------------------------------
    total_payment = fields.Monetary(compute='_compute_totals', store=True)
    total_interest = fields.Monetary(compute='_compute_totals', store=True)
    outstanding = fields.Monetary(
        compute='_compute_totals', store=True, string="Outstanding principal",
        help="Principal not yet repaid by a posted instalment.",
    )
    posted_count = fields.Integer(compute='_compute_totals', store=True)

    _principal_positive = models.Constraint(
        'CHECK(principal > 0)', "The principal must be greater than zero.")
    _rate_not_negative = models.Constraint(
        'CHECK(rate >= 0)', "The interest rate cannot be negative.")
    _term_positive = models.Constraint(
        'CHECK(term > 0)', "A loan needs at least one instalment.")

    @api.depends('line_ids.payment', 'line_ids.interest', 'line_ids.principal',
                 'line_ids.state')
    def _compute_totals(self):
        for loan in self:
            lines = loan.line_ids
            loan.total_payment = sum(lines.mapped('payment'))
            loan.total_interest = sum(lines.mapped('interest'))
            posted = lines.filtered(lambda line: line.state == 'posted')
            loan.posted_count = len(posted)
            loan.outstanding = loan.currency_id.round(
                loan.principal - sum(posted.mapped('principal')))

    # -- schedule ------------------------------------------------------------

    def _periods_per_year(self):
        return PERIODS_PER_YEAR[self.frequency]

    def _months_per_period(self):
        return 12 // self._periods_per_year()

    def _rate_per_period(self):
        """The nominal annual rate split evenly across the periods in a year.

        Simple division, not an effective-rate conversion. That is what Nepali
        bank sanction letters quote, and matching the lender's own arithmetic
        matters more here than compounding purity.
        """
        return (self.rate / 100.0) / self._periods_per_year()

    @staticmethod
    def _equal_instalment(principal, rate_per_period, periods):
        """The level payment that clears `principal` over `periods`."""
        if not rate_per_period:
            return principal / periods
        discount = (1.0 + rate_per_period) ** -periods
        return principal * rate_per_period / (1.0 - discount)

    def _build_schedule(self):
        """Return the schedule as a list of dicts, oldest first.

        The final instalment repays whatever principal is left rather than a
        recomputed figure. That is what makes the closing balance land on
        exactly zero instead of a few paisa either side, whichever method and
        rounding are in play.
        """
        self.ensure_one()
        currency = self.currency_id
        rate = self._rate_per_period()
        periods = self.term
        level_payment = (
            self._equal_instalment(self.principal, rate, periods)
            if self.method == 'emi' else 0.0
        )

        rows = []
        opening = self.principal
        for number in range(1, periods + 1):
            interest = currency.round(opening * rate)
            is_last = number == periods

            if is_last:
                principal_part = opening
            elif self.method == 'emi':
                principal_part = currency.round(level_payment - interest)
                if principal_part <= 0:
                    raise UserError(_(
                        "At %(rate)s%% over %(term)s instalments the payment "
                        "does not cover the interest, so this loan would never "
                        "be repaid. Lengthen the term or lower the rate.",
                        rate=self.rate, term=self.term,
                    ))
            elif self.method == 'equal_principal':
                principal_part = currency.round(self.principal / periods)
            else:  # interest_only
                principal_part = 0.0

            principal_part = min(principal_part, opening)
            closing = currency.round(opening - principal_part)
            rows.append({
                'sequence': number,
                'date': self.date_start + relativedelta(
                    months=self._months_per_period() * number),
                'opening_balance': opening,
                'interest': interest,
                'principal': principal_part,
                'payment': currency.round(principal_part + interest),
                'closing_balance': closing,
            })
            opening = closing
        return rows

    def action_compute_schedule(self):
        """Rebuild the schedule from the terms. Refuses to discard posted work."""
        for loan in self:
            posted = loan.line_ids.filtered(lambda line: line.state == 'posted')
            if posted:
                raise UserError(_(
                    "%(count)s instalments of '%(loan)s' are already posted, so "
                    "the schedule cannot be rebuilt. Reverse those entries "
                    "first, or record the change as a new loan.",
                    count=len(posted), loan=loan.name,
                ))
            loan.line_ids.unlink()
            loan.line_ids = [Command.create(row) for row in loan._build_schedule()]
        return True

    def action_confirm(self):
        for loan in self:
            if not loan.line_ids:
                loan.action_compute_schedule()
            loan.state = 'open'
        return True

    def action_cancel(self):
        for loan in self:
            if loan.line_ids.filtered(lambda line: line.state == 'posted'):
                raise UserError(_(
                    "'%s' has posted instalments and cannot be cancelled. "
                    "Reverse the entries first.", loan.name))
            loan.state = 'cancel'
        return True

    def action_draft(self):
        for loan in self:
            if loan.line_ids.filtered(lambda line: line.state == 'posted'):
                raise UserError(_(
                    "'%s' has posted instalments; it cannot go back to draft.",
                    loan.name))
            loan.state = 'draft'
        return True

    # -- posting -------------------------------------------------------------

    def _check_postable(self):
        self.ensure_one()
        if self.state != 'open':
            raise UserError(_(
                "'%s' is not running. Confirm it before posting entries.", self.name))

    def action_post_disbursement(self):
        """Money in: debit the bank, credit the loan liability."""
        for loan in self:
            loan._check_postable()
            if loan.disbursement_move_id:
                raise UserError(_(
                    "The drawdown of '%s' is already posted as %s.",
                    loan.name, loan.disbursement_move_id.name))
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'date': loan.date_start,
                'journal_id': loan.journal_id.id,
                'ref': _("%s - drawdown", loan.name),
                'company_id': loan.company_id.id,
                'line_ids': [
                    Command.create({
                        'name': _("%s - drawdown", loan.name),
                        'account_id': loan.payment_account_id.id,
                        'debit': loan.principal, 'credit': 0.0,
                        'partner_id': loan.partner_id.id,
                    }),
                    Command.create({
                        'name': _("%s - principal", loan.name),
                        'account_id': loan.loan_account_id.id,
                        'debit': 0.0, 'credit': loan.principal,
                        'partner_id': loan.partner_id.id,
                    }),
                ],
            })
            move.action_post()
            loan.disbursement_move_id = move
        return True

    def action_post_due(self):
        """Post every instalment whose date has arrived."""
        today = fields.Date.context_today(self)
        posted = self.env['l10n_np.loan.line']
        for loan in self:
            loan._check_postable()
            due = loan.line_ids.filtered(
                lambda line: line.state == 'draft' and line.date <= today)
            posted |= due
            due.action_post()
        if not posted:
            raise UserError(_("No instalment is due yet."))
        return True

    def action_view_moves(self):
        self.ensure_one()
        moves = self.line_ids.move_id | self.disbursement_move_id
        return {
            'type': 'ir.actions.act_window',
            'name': _("Entries of %s", self.name),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }


class LoanLine(models.Model):
    _name = 'l10n_np.loan.line'
    _description = 'Loan Instalment'
    _order = 'loan_id, sequence, id'

    loan_id = fields.Many2one(
        'l10n_np.loan', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='loan_id.company_id', store=True,
                                 index=True)  # SCH-1
    currency_id = fields.Many2one(related='loan_id.currency_id')
    partner_id = fields.Many2one(related='loan_id.partner_id', store=True)
    sequence = fields.Integer(string="No.", required=True)
    date = fields.Date(required=True, index=True)

    opening_balance = fields.Monetary()
    payment = fields.Monetary()
    principal = fields.Monetary()
    interest = fields.Monetary()
    closing_balance = fields.Monetary()

    move_id = fields.Many2one('account.move', readonly=True, copy=False)
    state = fields.Selection(
        [('draft', 'Scheduled'), ('posted', 'Posted')],
        default='draft', required=True, readonly=True,
    )

    def action_post(self):
        """One instalment: clear principal off the liability, expense the
        interest, and pay both out of the bank."""
        for line in self:
            if line.state == 'posted':
                raise UserError(_(
                    "Instalment %(number)s of '%(loan)s' is already posted as "
                    "%(move)s.",
                    number=line.sequence, loan=line.loan_id.name,
                    move=line.move_id.name,
                ))
            loan = line.loan_id
            loan._check_postable()

            values = []
            if line.principal:
                values.append(Command.create({
                    'name': _("%(loan)s - principal %(number)s",
                              loan=loan.name, number=line.sequence),
                    'account_id': loan.loan_account_id.id,
                    'debit': line.principal, 'credit': 0.0,
                    'partner_id': loan.partner_id.id,
                }))
            if line.interest:
                values.append(Command.create({
                    'name': _("%(loan)s - interest %(number)s",
                              loan=loan.name, number=line.sequence),
                    'account_id': loan.interest_account_id.id,
                    'debit': line.interest, 'credit': 0.0,
                    'partner_id': loan.partner_id.id,
                }))
            if not values:
                raise UserError(_(
                    "Instalment %(number)s of '%(loan)s' is zero, so there is "
                    "nothing to post.", number=line.sequence, loan=loan.name))
            values.append(Command.create({
                'name': _("%(loan)s - instalment %(number)s",
                          loan=loan.name, number=line.sequence),
                'account_id': loan.payment_account_id.id,
                'debit': 0.0, 'credit': line.payment,
                'partner_id': loan.partner_id.id,
            }))

            move = self.env['account.move'].create({
                'move_type': 'entry',
                'date': line.date,
                'journal_id': loan.journal_id.id,
                'ref': _("%(loan)s - instalment %(number)s",
                         loan=loan.name, number=line.sequence),
                'company_id': loan.company_id.id,
                'line_ids': values,
            })
            move.action_post()
            line.move_id = move
            line.state = 'posted'

            if all(other.state == 'posted' for other in loan.line_ids):
                loan.state = 'closed'
        return True
