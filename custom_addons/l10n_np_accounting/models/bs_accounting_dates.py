# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Render accounting dates in Bikram Sambat when the setting is on.

The `bs_date` widget from ``l10n_np_bs`` is normally opt-in per field, written
into a view by hand. An accountant working to a Nepali fiscal year wants it on
*every* accounting date at once, and wants to turn it off again without editing
views. So the widget is injected into the arch at read time, keyed on a group
that a Settings checkbox grants.

This follows the same seam Odoo core uses in ``res.currency``
(``base/models/res_currency.py``): override ``_get_view`` to adjust the arch and
extend ``_get_view_cache_key`` so the cached arch cannot leak between users who
differ on the setting.

Why not view inheritance with ``group_ids``
------------------------------------------
That is the obvious approach and it does gate correctly, but it needs an xpath
per field occurrence. ``account.view_move_form`` alone carries two separate
``invoice_date`` nodes (customer and vendor variants), so name-based xpaths
silently patch the first and miss the second. Walking the arch catches every
occurrence in every view without hard-coding positions that core is free to
change.

Storage is untouched. Only the presentation and the typed input are BS; the
column stays a Gregorian ``date``, so every domain, group-by, report and
reconciliation keeps working unchanged.
"""
from odoo import api, models

GROUP = 'l10n_np_accounting.group_bs_accounting_dates'


class BsDateViewMixin(models.AbstractModel):
    """Mix into a model and list its date fields in ``_BS_DATE_FIELDS``."""

    _name = 'l10n_np.bs.date.view.mixin'
    _description = 'Bikram Sambat date presentation'

    # Field names to render in BS. Deliberately an allowlist rather than "every
    # date field": an accounting app should be predictable, and some dates
    # (audit timestamps, technical dates) are not meaningful in BS.
    _BS_DATE_FIELDS = ()

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type='form', **options):
        """Two users can disagree about this setting, so the arch cache must
        distinguish them or one will be served the other's rendering. The digit
        style is company-level and also changes the arch, so it belongs here
        too."""
        key = super()._get_view_cache_key(view_id, view_type, **options)
        return key + (self.env.user.has_group(GROUP),
                      self.env.company.l10n_np_bs_digits)

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type not in ('form', 'list'):
            # Search panels and pivots have no editable date input to convert,
            # and a widget on a search field would be ignored anyway.
            return arch, view
        if not self.env.user.has_group(GROUP):
            return arch, view

        # Options are widget-specific, so they are replaced rather than merged:
        # anything the standard date widget was given (`warn_future` on
        # invoice_date, for instance) means nothing to `bs_date`.
        digits = self.env.company.l10n_np_bs_digits
        widget_options = "{'np_digits': %s}" % ('true' if digits == 'devanagari' else 'false')

        for name in self._BS_DATE_FIELDS:
            if name not in self._fields:
                # A field can disappear when an optional module is uninstalled.
                # Skip rather than fail: a missing date must not break the view.
                continue
            for node in arch.iter('field'):
                if node.get('name') != name or node.get('widget'):
                    # An explicit widget in the view is a deliberate choice
                    # (daterange, remaining_days); never override it.
                    continue
                node.set('widget', 'bs_date')
                node.set('options', widget_options)
        return arch, view


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'l10n_np.bs.date.view.mixin']

    # `date` is the field Odoo labels "Accounting Date".
    _BS_DATE_FIELDS = ('date', 'invoice_date', 'invoice_date_due', 'delivery_date')


class AccountMoveLine(models.Model):
    _name = 'account.move.line'
    _inherit = ['account.move.line', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('date', 'date_maturity')


class AccountPayment(models.Model):
    _name = 'account.payment'
    _inherit = ['account.payment', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('date',)


class AccountPaymentRegister(models.TransientModel):
    _name = 'account.payment.register'
    _inherit = ['account.payment.register', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('payment_date',)


class AccountBankStatement(models.Model):
    _name = 'account.bank.statement'
    _inherit = ['account.bank.statement', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('date',)


class AccountBankStatementLine(models.Model):
    _name = 'account.bank.statement.line'
    _inherit = ['account.bank.statement.line', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('date',)


class AccountLockDates(models.TransientModel):
    _name = 'account.lock.dates'
    _inherit = ['account.lock.dates', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('fiscalyear_lock_date', 'tax_lock_date', 'sale_lock_date',
                       'purchase_lock_date', 'hard_lock_date')


class FinancialStatementsWizard(models.TransientModel):
    _name = 'account.financial.statements.wizard'
    _inherit = ['account.financial.statements.wizard', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('date_from', 'date_to')


class VatReturn(models.Model):
    _name = 'l10n_np.vat.return'
    _inherit = ['l10n_np.vat.return', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('date_from', 'date_to')


class TdsCertificate(models.Model):
    _name = 'l10n_np.tds.certificate'
    _inherit = ['l10n_np.tds.certificate', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('date_from', 'date_to')


class TdsReturn(models.Model):
    _name = 'l10n_np.tds.return'
    _inherit = ['l10n_np.tds.return', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('date_from', 'date_to')


class Loan(models.Model):
    _name = 'l10n_np.loan'
    _inherit = ['l10n_np.loan', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('date_start',)


class LoanLine(models.Model):
    _name = 'l10n_np.loan.line'
    _inherit = ['l10n_np.loan.line', 'l10n_np.bs.date.view.mixin']

    _BS_DATE_FIELDS = ('date',)
