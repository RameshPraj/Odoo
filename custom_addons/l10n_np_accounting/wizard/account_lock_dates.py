# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountLockDates(models.TransientModel):
    """Edit a company's five accounting lock dates on one screen.

    Community defines all five fields on ``res.company`` and enforces them on
    every posting, but only surfaces them buried in Settings. This wizard is a
    thin editor over the same fields -- it adds no rules of its own.

    In particular the irreversibility of ``hard_lock_date`` is enforced by
    ``res.company.write`` itself (``account/models/company.py``), so writing
    through this wizard is exactly as safe as writing through Settings.
    """

    # Prefixed, not `account.lock.dates` (UPG-4). A model name without a
    # vendor prefix sits in Odoo's own namespace, and `_name` is not a
    # reservation -- if Odoo 20 introduces `account.lock.dates`, this class stops
    # *defining* a model and silently starts *extending* theirs, merging these
    # five fields into it. That failure is quiet and arrives during an upgrade,
    # which is the worst combination.
    #
    # Every other locally invented model in this suite is already prefixed
    # (`l10n_np.loan`, `l10n_np.tds.category`, `l10n_np.vat.return`,
    # `l10n_np.generate.fiscal.year`); this was the sole exception, on the
    # reasoning that it is a thin editor over core `res.company` fields. That
    # justifies the module it lives in, not the namespace it claims.
    _name = 'l10n_np.account.lock.dates'
    _description = 'Accounting Lock Dates'

    LOCK_FIELDS = (
        'fiscalyear_lock_date',
        'tax_lock_date',
        'sale_lock_date',
        'purchase_lock_date',
        'hard_lock_date',
    )

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )

    # Each date mirrors the company's current value and stays editable. This is
    # a computed default rather than a plain `default=`, because `default_get`
    # cannot see the values passed to `create()`: creating the wizard for one
    # company would otherwise load a *different* company's dates, and applying
    # it would clear the target company's locks.
    _LOCK_DATE = {'compute': '_compute_lock_dates', 'store': True,
                  'readonly': False, 'precompute': True}

    fiscalyear_lock_date = fields.Date(
        string="Global Lock Date", **_LOCK_DATE,
        help="No entry of any kind may be posted on or before this date.",
    )
    tax_lock_date = fields.Date(
        string="Tax Return Lock Date", **_LOCK_DATE,
        help="No entry carrying tax may be posted on or before this date. "
             "Set this once a VAT return has been filed for the period.",
    )
    sale_lock_date = fields.Date(
        string="Sales Lock Date", **_LOCK_DATE,
        help="No customer entry may be posted on or before this date.",
    )
    purchase_lock_date = fields.Date(
        **_LOCK_DATE,
        help="No vendor entry may be posted on or before this date.",
    )
    hard_lock_date = fields.Date(
        **_LOCK_DATE,
        help="Irreversible. Once set it can only be moved forward, never back, "
             "and no exception can be granted. Set it only after the accounts "
             "for the period have been finalised.",
    )

    @api.depends('company_id')
    def _compute_lock_dates(self):
        """Load the selected company's locks, so the form is an editor rather
        than a blank slate that would silently clear them.

        Depending on company_id also covers the multi-company case: switching
        company on the form reloads that company's dates instead of carrying the
        previous one's over.
        """
        for wizard in self:
            for name in self.LOCK_FIELDS:
                wizard[name] = wizard.company_id[name] if wizard.company_id else False

    def action_apply(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_("Only an Accounting Adviser may change lock dates."))
        # Write only what actually changed, so an unchanged hard lock date never
        # re-triggers core's irreversibility check.
        values = {
            name: self[name]
            for name in self.LOCK_FIELDS
            if self[name] != self.company_id[name]
        }
        if not values:
            return {'type': 'ir.actions.act_window_close'}
        self.company_id.sudo().write(values)
        return {'type': 'ir.actions.act_window_close'}
