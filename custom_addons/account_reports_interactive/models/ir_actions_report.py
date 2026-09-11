# -*- coding: utf-8 -*-
"""Keep self-contained accounting reports out of the layout setup wizard."""

from odoo import models


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def report_action(self, docids, data=None, config=True):
        self.ensure_one()
        if self.report_name.startswith("account_financial_report."):
            config = False
        return super().report_action(docids, data=data, config=config)
