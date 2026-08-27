# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class L10nNpBankMatching(models.TransientModel):
    """Clear an outstanding payment against a bank statement line.

    A payment posted through an Outstanding Receipts/Payments account is in two
    halves. The receivable half is cleared when the invoice is reconciled; the
    outstanding half sits on the balance sheet until the bank confirms the money
    actually moved. Confirming it means reconciling that line against a bank
    statement line -- and Community ships the engine for that without any caller:
    the screen lives in Enterprise ``account_accountant``, and the payment search
    view even offers a "No Bank Matching" filter (account_payment_view.xml:108)
    with no action behind it.

    This wizard is that missing caller. It performs the sequence Odoo itself
    publishes under LGPL-3 in its own test suite -- ``account/tests/common.py``'s
    ``pay_with_statement_line`` (:640-655) and ``test_account_payment.py:396-406``,
    the latter prefaced with "Reconcile without the bank reconciliation widget
    since the widget is in enterprise":

        resolve the statement line's counterpart onto the outstanding account,
        then reconcile it against the payment's outstanding line.

    It adds no accounting rules of its own. ``is_matched`` is a stored compute off
    ``move_id.line_ids.amount_residual`` (account_payment.py:469-497); nothing here
    writes it, and nothing here needs to.
    """

    _name = 'l10n_np.bank.matching'
    _description = 'Match an Outstanding Payment to the Bank'
    _check_company_auto = True

    # Not `required=True` at field level. Launched from a bank transaction the
    # wizard fills this in only when exactly one payment can offset it, so on a
    # journal with several open payments the field legitimately opens empty --
    # and a required-field error is a worse way to say "choose a payment" than
    # the first rung of `action_match`.
    payment_id = fields.Many2one(
        'account.payment', check_company=True,
        domain="[('is_matched', '=', False), ('state', 'in', ('in_process', 'paid'))]",
        help="The payment whose outstanding half is still on the balance sheet.",
    )
    # Not `related='payment_id.company_id'`. `payment_id` is legitimately empty
    # when the wizard opens from a bank transaction whose payment is ambiguous,
    # and a related company_id is then empty too -- at which point `check_company`
    # on `statement_line_id` fails with "belongs to company '' while ... belongs
    # to another company", refusing to open the form at all. A plain required
    # default is always populated, and is the same shape as account.lock.dates.
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    journal_id = fields.Many2one(related='payment_id.journal_id')
    currency_id = fields.Many2one(related='payment_id.currency_id')
    outstanding_account_id = fields.Many2one(
        related='payment_id.outstanding_account_id',
        string="Outstanding Account",
        help="The in-transit account this payment is waiting on. Matching moves "
             "the amount from here onto the bank account.",
    )
    partner_id = fields.Many2one(related='payment_id.partner_id')

    # The bank's own amount is not editable. A bank that credited a different
    # figure than the payment is a partial receipt, which needs a write-off line
    # and is deliberately out of scope -- see the module README. Displaying it
    # readonly keeps the screen honest about what will be posted.
    amount = fields.Monetary(
        compute='_compute_amount', currency_field='currency_id',
        help="Signed as it will appear on the bank: positive for money in.",
    )

    available_statement_line_ids = fields.Many2many(
        'account.bank.statement.line', compute='_compute_available_statement_line_ids',
        string="Matchable Bank Transactions",
    )
    available_statement_line_count = fields.Integer(
        compute='_compute_available_statement_line_ids')

    # `mode`, `statement_line_id`, `date` and `payment_ref` are editable computed
    # defaults rather than plain `default=`, for the reason recorded at
    # wizard/account_lock_dates.py:34 -- `default_get` cannot see the values passed
    # to `create()`, so a default derived from `payment_id` has to be a compute or
    # it reads a different payment's values (here: no payment at all, because the
    # wizard is created with payment_id already set).
    _FROM_PAYMENT = {'compute': '_compute_from_payment', 'store': True,
                     'readonly': False, 'precompute': True}

    mode = fields.Selection(
        [('existing', "Match an existing bank transaction"),
         ('create', "Record the bank transaction now")],
        string="How", required=True, **_FROM_PAYMENT,
        help="Match an existing transaction when the statement has already been "
             "entered or imported. Record one now when it has not.",
    )
    statement_line_id = fields.Many2one(
        'account.bank.statement.line', string="Bank Transaction",
        check_company=True, **_FROM_PAYMENT,
    )
    date = fields.Date(
        string="Bank Date", **_FROM_PAYMENT,
        help="The date the bank shows for this transaction.",
    )
    payment_ref = fields.Char(
        string="Bank Label", **_FROM_PAYMENT,
        help="The description the bank shows for this transaction.",
    )

    # ------------------------------------------------------------------
    # DEFAULTS
    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        """Accept being launched from either side of the match.

        Same shape as core's `account.payment.register` (account_payment_register.py
        :934-987): read `active_model`/`active_ids`, accept only the models this
        wizard understands, and refuse anything else rather than silently opening a
        blank form.
        """
        defaults = super().default_get(fields_list)
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids') or []
        if not active_model or not active_ids:
            return defaults

        if active_model == 'account.payment':
            if len(active_ids) > 1:
                raise UserError(_(
                    "Match one payment at a time. You selected %s.", len(active_ids)))
            defaults['payment_id'] = active_ids[0]
        elif active_model == 'account.bank.statement.line':
            if len(active_ids) > 1:
                raise UserError(_(
                    "Match one bank transaction at a time. You selected %s.",
                    len(active_ids)))
            st_line = self.env['account.bank.statement.line'].browse(active_ids[0])
            defaults['statement_line_id'] = st_line.id
            defaults['mode'] = 'existing'
            payment = self._suggest_payment(st_line)
            if payment:
                defaults['payment_id'] = payment.id
        else:
            raise UserError(_(
                "This screen matches a payment to a bank transaction. It cannot be "
                "opened from %s.", active_model))
        return defaults

    @api.model
    def _suggest_payment(self, st_line):
        """The single unmatched payment this transaction can only be, if there is one.

        Deliberately not a suggestion engine -- it fills the field when exactly one
        candidate offsets the transaction, and leaves it blank otherwise. Guessing
        between several would be worse than asking.
        """
        candidates = self.env['account.payment'].search([
            # Leads with is_matched/journal_id/company_id to hit core's
            # _unmatched_idx (account_payment.py:204).
            ('is_matched', '=', False),
            ('journal_id', '=', st_line.journal_id.id),
            ('company_id', '=', st_line.company_id.id),
            ('state', 'in', ('in_process', 'paid')),
            ('move_id', '!=', False),
            ('outstanding_account_id', '!=', False),
        ])
        offsetting = candidates.filtered(lambda pay: self._offsets(pay, st_line))
        return offsetting if len(offsetting) == 1 else self.env['account.payment']

    @api.model
    def _offsets(self, payment, st_line):
        """Whether reconciling these two would leave nothing behind."""
        payment_line = self._outstanding_line(payment)
        suspense_line = self._suspense_line(st_line)
        if not payment_line or not suspense_line:
            return False
        company_currency = payment.company_id.currency_id
        return company_currency.is_zero(payment_line.balance + suspense_line.balance)

    @api.model
    def _outstanding_line(self, payment):
        """The payment's in-transit line -- the one still on the balance sheet."""
        if not payment.move_id or not payment.outstanding_account_id:
            return self.env['account.move.line']
        liquidity_lines, _counterpart, _writeoff = payment._seek_for_lines()
        return liquidity_lines.filtered(
            lambda aml: aml.account_id == payment.outstanding_account_id
            and not aml.reconciled)

    @api.model
    def _suspense_line(self, st_line):
        """The statement line's unresolved counterpart.

        Read under `skip_account_move_synchronization`, as core's own helpers do
        (account/tests/common.py:651), so merely looking cannot trigger a sync.
        """
        _liquidity, suspense_lines, other_lines = st_line.with_context(
            skip_account_move_synchronization=True)._seek_for_lines()
        if len(suspense_lines) != 1 or other_lines:
            # Already resolved onto some other account, or in a shape this wizard
            # will not touch. `action_match` reports which.
            return self.env['account.move.line']
        return suspense_lines

    # ------------------------------------------------------------------
    # COMPUTES
    # ------------------------------------------------------------------
    @api.depends('payment_id')
    def _compute_amount(self):
        for wizard in self:
            line = self._outstanding_line(wizard.payment_id)
            wizard.amount = line.balance if line else wizard.payment_id.amount

    @api.depends('payment_id')
    def _compute_available_statement_line_ids(self):
        for wizard in self:
            payment = wizard.payment_id
            lines = self.env['account.bank.statement.line']
            if payment.journal_id and payment.outstanding_account_id:
                # `payment=payment` binds the loop variable into the lambda. The
                # filter runs before the next iteration either way, so this is not
                # a live bug -- but an unbound closure over a loop variable is one
                # edit away from being one, which is why ruff's B023 flags it.
                lines = self.env['account.bank.statement.line'].search([
                    ('journal_id', '=', payment.journal_id.id),
                    ('company_id', '=', payment.company_id.id),
                    ('is_reconciled', '=', False),
                ]).filtered(lambda st, payment=payment: self._offsets(payment, st))
            wizard.available_statement_line_ids = lines
            wizard.available_statement_line_count = len(lines)

    @api.depends('payment_id')
    def _compute_from_payment(self):
        """Seed the bank's facts from the payment, then let the user correct them.

        Depending on `payment_id` also means switching payment on the form reloads
        the new one's date and reference instead of carrying the previous one's
        over -- the same reasoning as _compute_lock_dates.
        """
        for wizard in self:
            payment = wizard.payment_id
            candidates = wizard.available_statement_line_ids
            wizard.statement_line_id = candidates[0] if len(candidates) == 1 else False
            wizard.mode = 'existing' if candidates else 'create'
            wizard.date = payment.date
            wizard.payment_ref = payment.memo or payment.name or False

    # ------------------------------------------------------------------
    # ACTION
    # ------------------------------------------------------------------
    def action_match(self):
        self.ensure_one()
        payment = self.payment_id
        account = payment.outstanding_account_id
        company_currency = payment.company_id.currency_id

        if not self.env.user.has_group('account.group_account_user'):
            raise UserError(_("Only an Accountant may match payments to the bank."))

        if not payment:
            raise UserError(_(
                "Choose the payment this bank transaction pays. Nothing on this "
                "journal matched it on amount, so it has to be picked by hand."))

        # ---- the payment is in a state that can be matched at all -----------
        if payment.state not in ('in_process', 'paid') or not payment.move_id:
            raise UserError(_(
                "%(payment)s has no journal entry yet, so there is nothing to match. "
                "A payment only posts its entry once it leaves draft.",
                payment=payment.display_name,
            ))

        if payment.is_matched:
            already = payment.reconciled_statement_line_ids
            raise UserError(_(
                "%(payment)s is already matched to the bank%(where)s.",
                payment=payment.display_name,
                where=_(", against %s", ", ".join(already.mapped('payment_ref')))
                if already else "",
            ))

        if not account:
            raise UserError(_(
                "%(payment)s does not use an outstanding account: it posts straight "
                "to %(bank)s, so there is no in-transit amount to clear and nothing "
                "to match.\n\n"
                "Set an Outstanding Receipts/Payments account on the payment method "
                "line in journal %(journal)s if you want the two-step treatment.",
                payment=payment.display_name,
                bank=payment.journal_id.default_account_id.display_name
                or _("the bank account"),
                journal=payment.journal_id.display_name,
            ))

        if not account.reconcile:
            raise UserError(_(
                "Matching is only allowed on accounts flagged 'Allow Reconciliation'. "
                "%(code)s %(name)s is not.\n\n"
                "Set the flag on the account, then try again.",
                code=account.code, name=account.display_name,
            ))

        # ---- single currency only (ACC-1) -----------------------------------
        journal_currency = payment.journal_id.currency_id or company_currency
        if payment.currency_id != company_currency or journal_currency != company_currency:
            raise UserError(_(
                "This screen handles company-currency payments only, and %(payment)s "
                "is in %(currency)s.\n\n"
                "Matching across currencies has to post the counterpart at the bank's "
                "rate rather than the system rate, which is a separate piece of work "
                "(ACC-1). Reconcile it by hand for now, rather than have this screen "
                "guess at the rate.",
                payment=payment.display_name, currency=payment.currency_id.name,
            ))

        payment_line = self._outstanding_line(payment)
        if not payment_line:
            raise UserError(_(
                "%(payment)s has no open line on %(account)s, so its in-transit "
                "amount is already gone. Check the journal entry: something has moved "
                "or reconciled it outside this screen.",
                payment=payment.display_name, account=account.display_name,
            ))

        # ---- and the two sides actually offset -------------------------------
        if self.mode == 'existing':
            st_line = self.statement_line_id
            if not st_line:
                raise UserError(_(
                    "Choose the bank transaction to match against, or switch to "
                    "'Record the bank transaction now' if the statement has not been "
                    "entered yet."))
            if st_line.journal_id != payment.journal_id:
                raise UserError(_(
                    "%(line)s is on journal %(line_journal)s but the payment is on "
                    "%(pay_journal)s. A payment can only be matched against its own "
                    "bank journal.",
                    line=st_line.display_name,
                    line_journal=st_line.journal_id.display_name,
                    pay_journal=payment.journal_id.display_name,
                ))
            if st_line.foreign_currency_id:
                raise UserError(_(
                    "%(line)s carries a foreign currency, which this screen does not "
                    "handle yet (ACC-1).", line=st_line.display_name))
            suspense_line = self._suspense_line(st_line)
            if not suspense_line:
                raise UserError(_(
                    "%(line)s has already been resolved onto another account, so there "
                    "is no unresolved counterpart left to match. Use Unmatch on the "
                    "transaction first if you want to redo it.",
                    line=st_line.display_name,
                ))
            if not company_currency.is_zero(payment_line.balance + suspense_line.balance):
                raise UserError(_(
                    "The amounts do not offset: the payment leaves %(payment_amount)s "
                    "outstanding and %(line)s is for %(line_amount)s.\n\n"
                    "This screen clears a payment in full. A bank amount that differs "
                    "from the payment needs a write-off, which has to be done by hand.",
                    payment_amount=payment_line.balance,
                    line=st_line.display_name,
                    line_amount=-suspense_line.balance,
                ))
        elif not self.date:
            raise UserError(_("Enter the date the bank shows for this transaction."))

        # ---- perform it ------------------------------------------------------
        if self.mode == 'create':
            # `counterpart_account_id` is popped by core's create
            # (account_bank_statement_line.py:393, "Hack to force different account
            # instead of the suspense account"), so the counterpart is never the
            # suspense account and there is no account to repoint afterwards.
            #
            # No `statement_id`: it is optional, and inventing a statement header to
            # hold one line would be inventing a bank document.
            st_line = self.env['account.bank.statement.line'].create({
                'journal_id': payment.journal_id.id,
                'date': self.date,
                'payment_ref': self.payment_ref or payment.display_name,
                'partner_id': payment.partner_id.id,
                'amount': payment_line.balance,
                'counterpart_account_id': account.id,
            })
            counterpart_line = st_line.move_id.line_ids.filtered(
                lambda aml: aml.account_id == account)
        else:
            # Repoint, then reconcile -- never the other way round. `account_id` is in
            # `reconciliation_fnames` (account_move_line.py:3477-3487), so writing it
            # on an already-reconciled line trips :1854-1879, which calls
            # remove_move_reconcile() and action_undo_reconciliation().
            suspense_line.account_id = account
            counterpart_line = suspense_line

        (counterpart_line + payment_line).reconcile()

        # The payment <-> statement line link needs no field of its own: core derives
        # `reconciled_statement_line_ids` from the partial reconcile itself
        # (account_payment.py:739-760, joining on outstanding_account_id and
        # counterpart_line.statement_line_id). Writing `st_line.payment_ids` would be
        # actively harmful -- `action_undo_reconciliation` does `payment_ids.unlink()`
        # (:465), which would arm a button that deletes the user's payment.

        # ---- then measure, rather than assume --------------------------------
        # Raising here rolls the whole thing back, which is the point: a statement
        # line that cleared nothing is worse than no statement line.
        payment.invalidate_recordset(['is_matched'])
        if not payment.is_matched:
            raise UserError(_(
                "The match did not clear %(payment)s: %(residual)s is still "
                "outstanding on %(account)s. Nothing has been saved.",
                payment=payment.display_name,
                residual=payment_line.amount_residual,
                account=account.display_name,
            ))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Matched to the bank"),
                'message': _(
                    "%(payment)s is matched against %(line)s. %(amount)s has moved off "
                    "%(account)s and onto the bank.",
                    payment=payment.display_name,
                    line=st_line.payment_ref or st_line.display_name,
                    amount=abs(payment_line.balance),
                    account=account.display_name,
                ),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
