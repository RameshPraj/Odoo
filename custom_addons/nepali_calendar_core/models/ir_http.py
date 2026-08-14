# -*- coding: utf-8 -*-
from odoo import models
from .res_users import CONTEXT_KEY


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Ship the resolved calendar to the web client.

        This is the correct channel for a *per-user* value. The tempting
        alternative -- `lang_params` via `_get_translations_for_webclient` -- is
        cached as `ormcache('frozenset(modules)', 'lang')` with **no uid** and is
        served `Cache-Control: public`, so a per-user value there would be
        cross-contaminated between users and cached by browsers and CDNs.
        """
        info = super().session_info()
        company = self.env.user.sudo().company_id
        info[CONTEXT_KEY] = self.env['res.users']._resolve_calendar_system()
        info['bs_digits'] = company.bs_digits
        return info
