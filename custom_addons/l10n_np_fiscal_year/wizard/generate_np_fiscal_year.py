# -*- coding: utf-8 -*-
"""Generate account.fiscal.year records for Nepali fiscal years.

A Nepali fiscal year runs Shrawan 1 of BS year N to Ashar end of BS year N+1.
Both endpoints are derived from the Bikram Sambat calendar, so the Gregorian
dates are exact for every year rather than an approximation.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Bikram Sambat month numbers
SHRAWAN = 4   # first month of the fiscal year
ASHAR = 3     # last month of the fiscal year


class GenerateNPFiscalYear(models.TransientModel):
    _name = 'l10n_np.generate.fiscal.year'
    _description = 'Generate Nepali Fiscal Years'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    bs_year_from = fields.Integer(
        string='From BS Year', required=True, default=lambda self: self._default_bs_year(),
        help="First fiscal year to generate, e.g. 2083 creates FY 2083/84.",
    )
    bs_year_to = fields.Integer(
        string='To BS Year', required=True, default=lambda self: self._default_bs_year() + 4,
    )
    overwrite = fields.Boolean(
        string='Replace existing',
        help="Delete and recreate fiscal years that overlap the generated range. "
             "Leave unticked to skip years that already exist.",
    )
    preview = fields.Text(readonly=True)

    @api.model
    def _default_bs_year(self):
        from odoo.addons.l10n_np_bs.tools import bs  # noqa: PLC0415
        y, m, _d = bs.ad_to_bs(fields.Date.context_today(self))
        # before Shrawan we are still inside the previous fiscal year
        return y if m >= SHRAWAN else y - 1

    # ------------------------------------------------------------------
    # computation
    # ------------------------------------------------------------------
    @api.model
    def _fiscal_year_range(self, bs_year):
        """Return (name, date_from, date_to) for the fiscal year starting in ``bs_year``."""
        from odoo.addons.l10n_np_bs.tools import bs  # noqa: PLC0415

        date_from = bs.bs_to_ad(bs_year, SHRAWAN, 1)
        last_day = bs.month_length(bs_year + 1, ASHAR)
        date_to = bs.bs_to_ad(bs_year + 1, ASHAR, last_day)
        name = f"FY {bs_year}/{str(bs_year + 1)[-2:]} (Shrawan-Ashar)"
        return name, date_from, date_to

    @api.onchange('bs_year_from', 'bs_year_to')
    def _onchange_preview(self):
        for wiz in self:
            if not (wiz.bs_year_from and wiz.bs_year_to) or wiz.bs_year_to < wiz.bs_year_from:
                wiz.preview = False
                continue
            rows = []
            try:
                for y in range(wiz.bs_year_from, wiz.bs_year_to + 1):
                    name, d1, d2 = wiz._fiscal_year_range(y)
                    rows.append(f"{name:<30} {d1} -> {d2}   ({(d2 - d1).days + 1} days)")
            except UserError as exc:
                rows.append(str(exc))
            wiz.preview = "\n".join(rows)

    # ------------------------------------------------------------------
    # action
    # ------------------------------------------------------------------
    def action_generate(self):
        self.ensure_one()
        if self.bs_year_to < self.bs_year_from:
            raise UserError(_("'To BS Year' must not be earlier than 'From BS Year'."))

        FiscalYear = self.env['account.fiscal.year']
        created = self.env['account.fiscal.year']
        skipped = []

        for bs_year in range(self.bs_year_from, self.bs_year_to + 1):
            name, date_from, date_to = self._fiscal_year_range(bs_year)

            overlapping = FiscalYear.search([
                ('company_id', '=', self.company_id.id),
                ('date_from', '<=', date_to),
                ('date_to', '>=', date_from),
            ])
            if overlapping:
                if not self.overwrite:
                    skipped.append(name)
                    continue
                overlapping.unlink()

            created |= FiscalYear.create({
                'name': name,
                'date_from': date_from,
                'date_to': date_to,
                'company_id': self.company_id.id,
            })

        # Keep the built-in fallback consistent with the generated years, for any
        # code path that does not consult account.fiscal.year records.
        if created:
            last = max(created, key=lambda f: f.date_to)
            self.company_id.write({
                'fiscalyear_last_day': last.date_to.day,
                'fiscalyear_last_month': str(last.date_to.month),
            })

        if not created and skipped:
            raise UserError(_(
                "Nothing generated. These fiscal years already exist: %s\n\n"
                "Tick 'Replace existing' to regenerate them.",
                ", ".join(skipped),
            ))

        return {
            'type': 'ir.actions.act_window',
            'name': _("Nepali Fiscal Years"),
            'res_model': 'account.fiscal.year',
            'view_mode': 'list,form',
            'domain': [('company_id', '=', self.company_id.id)],
        }
