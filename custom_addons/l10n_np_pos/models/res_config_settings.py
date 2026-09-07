# -*- coding: utf-8 -*-
"""Surface the walk-in customer where a shop owner will look for it.

`pos.config` fields reach Settings through a `pos_`-prefixed related field on
`res.config.settings`, which is the convention core uses throughout
(`point_of_sale/models/res_config_settings.py:45-46`). Following it rather than
adding the field to the `pos.config` form directly, because the PoS section of
Settings is where every other till option lives and a setting nobody can find is
a setting nobody uses -- which, for this one, means invoices being refused with
no obvious remedy.
"""
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_np_pos_default_partner_id = fields.Many2one(
        related='pos_config_id.np_pos_default_partner_id', readonly=False)
