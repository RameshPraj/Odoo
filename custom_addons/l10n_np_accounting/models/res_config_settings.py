# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # A `group_`-prefixed settings field with `implied_group` is Odoo's own
    # mechanism for "a checkbox that grants a group": ticking it adds the group
    # to `base.group_user`, unticking removes it. No extra code needed.
    group_l10n_np_bs_accounting_dates = fields.Boolean(
        string="Bikram Sambat accounting dates",
        implied_group='l10n_np_accounting.group_bs_accounting_dates',
        help="Show and accept accounting dates in Bikram Sambat: the Accounting "
             "Date and due dates on entries, invoices and bills, journal item "
             "dates, payment dates, lock dates and the date ranges on the Nepal "
             "reports and returns.\n\n"
             "Dates are still stored as Gregorian, so reports, filters, "
             "group-by and reconciliation are unaffected. This changes only what "
             "is displayed and what may be typed.",
    )

    l10n_np_bs_digits = fields.Selection(
        related='company_id.l10n_np_bs_digits', readonly=False,
        help="Numerals used to draw Bikram Sambat dates. Latin ties back to a "
             "bank statement more easily; Devanagari reads as properly Nepali "
             "on a printed document.",
    )
