# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import _, models
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    """Give Community's reconciliation engine a button.

    ``account.move.line.reconcile()`` is public in Community and does the whole
    job -- partial matches, full matches, exchange-difference moves. What
    Community does not ship is any way to *call* it: the drag-and-drop
    reconciliation widget lives in Enterprise ``account_accountant``.

    This adds a header button to the Journal Items list. It is not a
    reimplementation of that widget; it is one button that calls the engine
    already present, after checking the preconditions the engine assumes so the
    user gets a sentence instead of a traceback.
    """

    _inherit = 'account.move.line'

    def _reconcile_candidates(self):
        """The lines the user actually selected, whichever way the button fired."""
        if self:
            return self
        return self.browse(self.env.context.get('active_ids', []))

    def action_reconcile_selected(self):
        lines = self._reconcile_candidates()
        if len(lines) < 2:
            raise UserError(_(
                "Select at least two journal items to reconcile against each other."
            ))

        not_posted = lines.filtered(lambda aml: aml.parent_state != 'posted')
        if not_posted:
            raise UserError(_(
                "Only posted entries can be reconciled. These are not posted yet:\n%s",
                "\n".join(f"- {aml.move_id.name or _('draft entry')}"
                          for aml in not_posted[:10]),
            ))

        not_reconcilable = lines.filtered(lambda aml: not aml.account_id.reconcile)
        if not_reconcilable:
            raise UserError(_(
                "Reconciliation is only allowed on accounts flagged 'Allow "
                "Reconciliation'. These accounts are not:\n%s\n\n"
                "Set the flag on the account, or exclude those lines.",
                "\n".join(sorted({
                    f"- {aml.account_id.code} {aml.account_id.display_name}"
                    for aml in not_reconcilable
                })),
            ))

        accounts = lines.account_id
        if len(accounts) > 1:
            raise UserError(_(
                "All selected items must sit on one account. You selected %(count)s:\n%(accounts)s",
                count=len(accounts),
                accounts="\n".join(f"- {a.code} {a.display_name}" for a in accounts),
            ))

        already_done = lines.filtered(lambda aml: aml.reconciled)
        if already_done:
            raise UserError(_(
                "%s of the selected items are already fully reconciled. "
                "Filter on 'With residual' to see only what is still open.",
                len(already_done),
            ))

        lines.reconcile()

        matched = len(lines.filtered(lambda aml: aml.reconciled))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Reconciled"),
                'message': _(
                    "%(matched)s of %(total)s items are now fully reconciled. "
                    "Any item still showing a residual was only partly matched.",
                    matched=matched, total=len(lines),
                ),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
