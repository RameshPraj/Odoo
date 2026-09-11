# -*- coding: utf-8 -*-
from odoo import fields, models

CALENDAR_SELECTION = [
    ('ad', "Gregorian (AD)"),
    ('bs', "Bikram Sambat (BS)"),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    calendar_system = fields.Selection(
        CALENDAR_SELECTION,
        string="Default Calendar",
        default='ad',
        required=True,
        help="Calendar used by staff who have not chosen one of their own.\n"
             "Resolution order is: the user's own preference, then this, then "
             "Gregorian.",
    )
    bs_digits = fields.Selection(
        [('latin', "Latin (2083-04-29)"),
         ('devanagari', "Devanagari (२०८३-०४-२९)")],
        string="Bikram Sambat digits",
        default='latin',
        required=True,
        help="Numerals used to draw Bikram Sambat dates. Latin ties back to a "
             "bank statement more easily; Devanagari reads as properly Nepali "
             "on a printed document.",
    )
    bs_report_output = fields.Selection(
        [('ad', "Gregorian only"),
         ('bs', "Bikram Sambat only"),
         ('both', "Both, e.g. 2083-04-29 BS (2026-08-14 AD)")],
        string="Dates on printed documents",
        default='both',
        required=True,
        help="How dates are printed on invoices, statements and certificates.\n"
             "'Both' is the safe default for statutory documents: the BS date is "
             "what a Nepali reader expects, and the AD date keeps the document "
             "reconcilable against banking and audit records.",
    )
