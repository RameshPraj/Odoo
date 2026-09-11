# -*- coding: utf-8 -*-
"""Bikram Sambat in printed output.

`t-field` and `t-out t-options-widget` dispatch to ``ir.qweb.field.<type>``, which
``ir_qweb.py`` documents as the extension point for customising rendering. That
makes these two overrides the one place where reports, website and portal date
output can be redirected -- previously there was none at all, and every PDF
rendered Gregorian while the screen showed BS.

Two things are deliberately NOT done here:

* ``tools.misc.format_date`` is not monkeypatched. There are 218 unfunnelled call
  sites and roughly fifteen of them build legal e-invoicing payloads (UBL/CII,
  TicketBAI) which must stay Gregorian.
* ``convert_to_export`` / ``convert_to_display_name`` are not touched. The former
  calls the latter, so overriding either silently rewrites every CSV and XLSX
  export and breaks re-import round-trips.

Note the asymmetry being handled: ``ir.qweb.field.date`` delegates to
``tools.format_date``, while ``ir.qweb.field.datetime`` calls Babel directly. They
share no implementation, so both need overriding -- patching only one leaves a
confusing half-translated document.
"""
from odoo import api, models
from odoo.fields import Datetime as DatetimeField

from ..tools import bs

# Note: printed output follows the *company* setting (`bs_report_output`), not the
# reader's personal preference. A printed invoice must not change depending on who
# pressed Print.


class IrQwebFieldDate(models.AbstractModel):
    _inherit = 'ir.qweb.field.date'

    @api.model
    def value_to_html(self, value, options):
        ad = super().value_to_html(value, options)
        if not value:
            return ad
        return self.env['ir.qweb.field.date']._bs_decorate(value, ad, options)

    @api.model
    def _bs_decorate(self, value, ad_text, options):
        """Render `value` per the company's output mode.

        `options` may carry `calendar` to force a mode for one specific field,
        which is what lets a document print one date in AD deliberately (a
        cheque date, say) while the rest follow the setting.
        """
        company = self.env.company
        mode = options.get('calendar') or company.bs_report_output or 'ad'
        if mode == 'ad':
            return ad_text
        bs_text = bs.format_bs(
            value, np_digits=company.bs_digits == 'devanagari',
        )
        if mode == 'bs':
            return f"{bs_text} BS"
        return f"{bs_text} BS ({ad_text} AD)"


class IrQwebFieldDatetime(models.AbstractModel):
    _inherit = 'ir.qweb.field.datetime'

    @api.model
    def value_to_html(self, value, options):
        ad = super().value_to_html(value, options)
        if not value:
            return ad
        # A Datetime arrives naive-UTC. It MUST be shifted into the reader's
        # timezone before the BS day is derived: converting UTC straight to BS
        # yields the wrong day for the 5h45m window before midnight in Kathmandu.
        local = DatetimeField.context_timestamp(self, DatetimeField.to_datetime(value))
        return self.env['ir.qweb.field.date']._bs_decorate(local.date(), ad, options)


class IrQweb(models.AbstractModel):
    _inherit = 'ir.qweb'

    def _prepare_environment(self, values):
        # Core mutates `values` in place and returns a re-contexted recordset, so
        # the helper is added after the super call rather than before it.
        result = super()._prepare_environment(values)
        values['format_date_bs'] = result._format_date_bs
        return result

    @api.model
    def _format_date_bs(self, value, np_digits=None, month_names=False):
        """Explicit helper for templates that format a date themselves.

        Added as a NEW name rather than shadowing `format_date`: shadowing would
        silently change every existing mail template, invoice and EDI document.
        """
        if not value:
            return ""
        if np_digits is None:
            np_digits = self.env.company.bs_digits == 'devanagari'
        return bs.format_bs(value, np_digits=np_digits, month_names=month_names)
