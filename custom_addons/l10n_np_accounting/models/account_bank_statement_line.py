# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import _, models
from odoo.exceptions import UserError


class AccountBankStatementLine(models.Model):
    """The matching entry point, and a guard against silently undoing a match.

    Community resolves a statement line by moving its suspense line onto the
    account the transaction really belongs to. Nothing in core objects to that --
    ``_synchronize_from_moves`` only guards against *more than one* suspense line
    (account_bank_statement_line.py:750), never against none.

    But ``_synchronize_to_moves`` (:793-832) rebuilds ``line_ids`` from
    ``_prepare_move_line_default_vals()`` **with no counterpart account**: it
    appends ``(0, 0, ...)`` to recreate a suspense line and ``(2, line.id)`` for
    every ``other_line``. On a resolved line the matched counterpart *is* an
    ``other_line``, so it gets unlinked -- and ``account_move_line.unlink`` begins
    with ``remove_move_reconcile()``. The match dissolves, the payment reverts to
    ``is_matched = False``, and nothing is raised. Unlike the payment's version
    (account_payment.py:1004-1005) this one has no ``state == 'posted'`` guard, so
    a posted, matched, reconciled entry is rewritten without complaint.

    It fires on six fields, and one of them is Partner -- an edit a user would
    reasonably make on a bank transaction long after matching it. So editing those
    six on a matched line is refused here, with Unmatch offered as the way through.
    Refusing rather than skipping the sync: skipping would leave the line's own
    ``amount`` out of step with the move it is supposed to mirror, which is a
    quieter and worse kind of wrong.
    """

    _inherit = 'account.bank.statement.line'

    #: The fields whose write rebuilds `line_ids`. Copied from the guard at
    #: account_bank_statement_line.py:800-804 -- if core ever adds one there and
    #: not here, the guard silently stops covering it, which
    #: tests/test_bank_matching.py asserts against.
    _SYNC_TRIGGER_FIELDS = frozenset((
        'payment_ref', 'amount', 'amount_currency',
        'foreign_currency_id', 'currency_id', 'partner_id',
    ))

    def _synchronize_to_moves(self, changed_fields):
        if not self.env.context.get('skip_account_move_synchronization') \
                and self._SYNC_TRIGGER_FIELDS.intersection(changed_fields):
            for st_line in self:
                matched = st_line._matched_counterpart_lines()
                if matched:
                    raise UserError(_(
                        "%(line)s is matched to the bank, so %(fields)s cannot be "
                        "changed: doing so would rebuild the journal entry and "
                        "silently undo the match.\n\n"
                        "Press Unmatch on the transaction, make the change, then "
                        "match it again.",
                        line=st_line.display_name,
                        fields=", ".join(sorted(
                            self._SYNC_TRIGGER_FIELDS.intersection(changed_fields))),
                    ))
        return super()._synchronize_to_moves(changed_fields)

    def _matched_counterpart_lines(self):
        """The resolved counterpart of this transaction, if it has been matched.

        Empty while a suspense line is still present, because then the transaction
        has not been resolved onto anything and there is nothing to protect.
        """
        self.ensure_one()
        _liquidity, suspense_lines, other_lines = self.with_context(
            skip_account_move_synchronization=True)._seek_for_lines()
        if suspense_lines:
            return self.env['account.move.line']
        return other_lines.filtered(
            lambda aml: aml.matched_debit_ids or aml.matched_credit_ids)

    # ------------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------------
    def action_l10n_np_match_payment(self):
        """Open the matching wizard for this transaction.

        The act_window is built here rather than declared as a record, following
        core's own `action_register_payment` (account_move_line.py:1362-1380): the
        wizard reads `active_model`/`active_ids` from the context, so the launcher
        has to set them.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Match Outstanding Payment"),
            'res_model': 'l10n_np.bank.matching',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                **self.env.context,
                'active_model': 'account.bank.statement.line',
                'active_ids': self.ids,
                'active_id': self.id,
            },
        }

    def action_unmatch(self):
        """Undo a match: break the reconciliation, put the counterpart back on suspense.

        Deliberately not core's `action_undo_reconciliation` (:460-472), which does
        `self.payment_ids.unlink()` and would therefore **delete** any payment listed
        there. This module never writes `payment_ids` for exactly that reason, but a
        button offered next to a payment must not be one keystroke away from
        deleting it.

        Order matters: unreconcile first, repoint second. `account_id` is in
        `reconciliation_fnames` (account_move_line.py:3477-3487), so writing it on a
        still-reconciled line trips :1854-1879, which calls both
        `remove_move_reconcile()` and `action_undo_reconciliation()` -- the very
        method being avoided.
        """
        for st_line in self:
            counterpart = st_line._matched_counterpart_lines()
            if not counterpart:
                raise UserError(_(
                    "%(line)s is not matched to anything, so there is nothing to "
                    "undo.", line=st_line.display_name))
            if len(counterpart) > 1:
                raise UserError(_(
                    "%(line)s has %(count)s matched lines. This was not produced by "
                    "the matching screen, so it is left alone -- unreconcile it by "
                    "hand from the journal entry.",
                    line=st_line.display_name, count=len(counterpart)))
            suspense_account = st_line.journal_id.suspense_account_id
            if not suspense_account:
                raise UserError(_(
                    "Journal %(journal)s has no suspense account, so the transaction "
                    "has nowhere to go back to. Set one on the journal first.",
                    journal=st_line.journal_id.display_name))
            counterpart.remove_move_reconcile()
            counterpart.account_id = suspense_account

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Unmatched"),
                'message': _(
                    "%s transactions are back on the suspense account and can be "
                    "matched again.", len(self)),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
