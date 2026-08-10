# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Which numerals Bikram Sambat dates are drawn with. Company-level rather
    # than hard-coded, because it is a house style rather than a fact: Latin
    # digits are easier to tie back to a bank statement, Devanagari reads as
    # properly Nepali on a printed document. Latin is the default because it is
    # the less surprising change to an existing ledger.
    l10n_np_bs_digits = fields.Selection(
        [('latin', "Latin (2083-05-24)"),
         ('devanagari', "Devanagari (२०८३-०५-२४)")],
        string="Bikram Sambat digits",
        default='latin', required=True,
    )
