# -*- coding: utf-8 -*-
"""TDS certificates issued to payees, and the periodic TDS return.

Amounts are read from Odoo's own withholding lines (account.withholding.line,
from l10n_account_withholding_tax) rather than recomputed, so a certificate can
never disagree with the ledger.

The certificate LAYOUT is a placeholder. The statutory format must be confirmed
by an accountant; see README.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TdsCertificate(models.Model):
    _name = 'l10n_np.tds.certificate'
    _description = 'Nepal TDS Certificate'
    _order = 'date_to desc, partner_id'
    _inherit = ['mail.thread']

    name = fields.Char(
        required=True, copy=False, readonly=True, default=lambda self: _('New'))
    partner_id = fields.Many2one('res.partner', string='Payee', required=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True)

    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)

    state = fields.Selection(
        [('draft', 'Draft'), ('issued', 'Issued'), ('cancel', 'Cancelled')],
        default='draft', tracking=True)

    line_ids = fields.One2many(
        'l10n_np.tds.certificate.line', 'certificate_id', readonly=True)
    amount_base = fields.Monetary(compute='_compute_amounts', store=True)
    amount_tds = fields.Monetary(compute='_compute_amounts', store=True)

    note = fields.Text()

    @api.depends('line_ids.amount_base', 'line_ids.amount_tds')
    def _compute_amounts(self):
        for rec in self:
            rec.amount_base = sum(rec.line_ids.mapped('amount_base'))
            rec.amount_tds = sum(rec.line_ids.mapped('amount_tds'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'l10n_np.tds.certificate') or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    def action_collect_lines(self):
        """Populate from the withholding lines actually posted in the period.

        Reads the ledger rather than recomputing, so the certificate cannot
        disagree with the accounts.
        """
        WithholdingLine = self.env['account.withholding.line']
        for cert in self:
            cert.line_ids.unlink()
            domain = [
                ('company_id', '=', cert.company_id.id),
                ('date', '>=', cert.date_from),
                ('date', '<=', cert.date_to),
            ]
            try:
                lines = WithholdingLine.search(domain)
            except Exception as exc:      # field names differ across versions
                raise UserError(_(
                    "Could not read withholding lines: %s\n\n"
                    "Check that 'l10n_account_withholding_tax' is installed.", exc)) from exc

            lines = lines.filtered(
                lambda l: l.partner_id == cert.partner_id if 'partner_id' in l._fields else True)
            if not lines:
                raise UserError(_(
                    "No withholding was recorded for %(partner)s between "
                    "%(d1)s and %(d2)s.",
                    partner=cert.partner_id.display_name,
                    d1=cert.date_from, d2=cert.date_to))

            for line in lines:
                cert.env['l10n_np.tds.certificate.line'].create({
                    'certificate_id': cert.id,
                    'name': line.display_name,
                    'date': line.date if 'date' in line._fields else cert.date_to,
                    'amount_base': abs(getattr(line, 'base_amount', 0.0) or 0.0),
                    'amount_tds': abs(getattr(line, 'amount', 0.0) or 0.0),
                })
        return True

    def action_issue(self):
        for cert in self:
            if not cert.line_ids:
                raise UserError(_("Collect the withholding lines before issuing."))
        self.write({'state': 'issued'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})


class TdsCertificateLine(models.Model):
    _name = 'l10n_np.tds.certificate.line'
    _description = 'Nepal TDS Certificate Line'
    _order = 'date, id'

    certificate_id = fields.Many2one(
        'l10n_np.tds.certificate', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='certificate_id.company_id', store=True)
    currency_id = fields.Many2one(related='certificate_id.currency_id')
    name = fields.Char(required=True)
    date = fields.Date(required=True)
    category_id = fields.Many2one('l10n_np.tds.category', string='TDS category')
    amount_base = fields.Monetary()
    amount_tds = fields.Monetary(string='TDS withheld')


class TdsReturn(models.Model):
    _name = 'l10n_np.tds.return'
    _description = 'Nepal TDS Return'
    _order = 'date_to desc'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('filed', 'Filed')], default='draft')
    certificate_ids = fields.Many2many('l10n_np.tds.certificate', string='Certificates')
    amount_total = fields.Monetary(compute='_compute_total', store=True)

    @api.depends('certificate_ids.amount_tds')
    def _compute_total(self):
        for rec in self:
            rec.amount_total = sum(rec.certificate_ids.mapped('amount_tds'))
