# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import _, models


class AccountPayment(models.Model):
    """Launch the matching wizard from the payment that is stuck.

    Community already ships the diagnosis: the payment search view carries a
    "No Bank Matching" filter (account_payment_view.xml:108) and there is an index
    built for that exact query (account_payment.py:204). What it does not ship is
    anything to do about a payment the filter finds -- that button is in Enterprise
    ``account_accountant``. This is it.
    """

    _inherit = 'account.payment'

    def action_l10n_np_match_to_bank(self):
        """Open the matching wizard for this payment.

        Built in Python rather than declared as an act_window record, following
        core's `action_register_payment` (account_move_line.py:1362-1380): the
        wizard reads `active_model`/`active_ids`, so the launcher must set them.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Match to Bank"),
            'res_model': 'l10n_np.bank.matching',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                **self.env.context,
                'active_model': 'account.payment',
                'active_ids': self.ids,
                'active_id': self.id,
            },
        }
