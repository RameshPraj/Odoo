# -*- coding: utf-8 -*-
"""TDS (withholding tax) rate schedule for Nepal.

DESIGN INTENT — READ BEFORE EDITING
-----------------------------------
This module ships with an EMPTY rate table on purpose. Nepali TDS rates,
thresholds and exemptions are set by the Income Tax Act and amended by Finance
Acts; they are not knowledge that belongs in source code. Encoding a guessed rate
would produce wrong filings.

Rates are therefore records that an accountant maintains through the UI, each
bounded by effective dates so that:

  * a Finance Act change is a new record, not a code change, and
  * returns for a past period still compute on the rate that applied then.

``_rate_for_date()`` is the single lookup used everywhere. Nothing in this module
hardcodes a percentage.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class TdsCategory(models.Model):
    _name = 'l10n_np.tds.category'
    _description = 'Nepal TDS Category'
    _order = 'code, date_from desc'

    name = fields.Char(required=True, help="Nature of payment, e.g. 'Rent', 'Service fee'.")
    code = fields.Char(
        required=True,
        help="Short code used on certificates and returns. Groups the versions of "
             "one category across rate changes.",
    )
    description = fields.Text()
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    # --- the values an accountant maintains -----------------------------
    rate = fields.Float(
        string='Rate (%)', required=True, digits=(5, 3),
        help="Withholding percentage applied to the payment base.",
    )
    threshold = fields.Monetary(
        string='Annual threshold',
        help="Withhold only once cumulative payments to the payee in the fiscal "
             "year exceed this amount. Zero means always withhold.",
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True)

    date_from = fields.Date(
        string='Effective from', required=True,
        help="First date this rate applies. Required so historical returns stay correct.",
    )
    date_to = fields.Date(
        string='Effective to',
        help="Leave empty while this is the current rate.",
    )

    # --- accounting wiring ----------------------------------------------
    account_id = fields.Many2one(
        'account.account', string='TDS payable account', required=True,
        domain="[('company_ids', 'in', company_id)]",
        help="Liability account credited with the amount withheld.",
    )
    tax_id = fields.Many2one(
        'account.tax', string='Withholding tax',
        domain="[('company_id', '=', company_id), ('is_withholding_tax_on_payment', '=', True)]",
        help="Optional link to the account.tax record used at payment time.",
    )

    legal_reference = fields.Char(
        help="Section of the Act or Finance Act this rate derives from. "
             "Recorded for audit; not validated by the system.",
    )

    # Odoo 19 replaced the _sql_constraints list with models.Constraint class
    # attributes. A legacy _sql_constraints list is silently ignored, so the
    # check never reaches the database.
    _rate_positive = models.Constraint(
        'CHECK(rate >= 0)',
        "The TDS rate cannot be negative.",
    )
    _rate_sane = models.Constraint(
        'CHECK(rate <= 100)',
        "A TDS rate above 100% is almost certainly a data-entry error.",
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError(_(
                    "On TDS category %s the effective-to date precedes effective-from.",
                    rec.display_name))

    @api.constrains('code', 'date_from', 'date_to', 'company_id')
    def _check_no_overlap(self):
        """Two rates for the same code must not cover the same day."""
        for rec in self:
            others = self.search([
                ('id', '!=', rec.id),
                ('code', '=', rec.code),
                ('company_id', '=', rec.company_id.id),
            ])
            for other in others:
                starts_before_other_ends = (
                    not other.date_to or rec.date_from <= other.date_to)
                ends_after_other_starts = (
                    not rec.date_to or rec.date_to >= other.date_from)
                if starts_before_other_ends and ends_after_other_starts:
                    raise ValidationError(_(
                        "TDS code %(code)s has two rates covering the same dates "
                        "(%(a)s and %(b)s). Close the earlier one with an "
                        "'Effective to' date first.",
                        code=rec.code, a=other.display_name, b=rec.display_name))

    @api.depends('name', 'code', 'rate', 'date_from')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"[{rec.code}] {rec.name} — {rec.rate}% from {rec.date_from}"

    # ------------------------------------------------------------------
    @api.model
    def _rate_for_date(self, code, date, company=None):
        """The single rate lookup. Returns the category in force on ``date``."""
        company = company or self.env.company
        rec = self.search([
            ('code', '=', code),
            ('company_id', '=', company.id),
            ('date_from', '<=', date),
            '|', ('date_to', '=', False), ('date_to', '>=', date),
        ], limit=1)
        if not rec:
            raise UserError(_(
                "No TDS rate is configured for code '%(code)s' on %(date)s.\n\n"
                "An authorised user must add it under Accounting Nepal > "
                "Configuration > TDS Categories. Rates are deliberately not "
                "shipped with this module because they are set by law.",
                code=code, date=date))
        return rec

    @api.model
    def _is_configured(self, company=None):
        company = company or self.env.company
        return bool(self.search_count([('company_id', '=', company.id)]))
