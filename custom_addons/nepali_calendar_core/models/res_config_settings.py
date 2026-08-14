# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Mirrors of the company fields. The company record is the single source of
    # truth -- these are `related`, so there is no second copy to drift.
    calendar_system = fields.Selection(
        related='company_id.calendar_system', readonly=False, required=True,
    )
    bs_digits = fields.Selection(
        related='company_id.bs_digits', readonly=False, required=True,
    )
    bs_report_output = fields.Selection(
        related='company_id.bs_report_output', readonly=False, required=True,
    )
