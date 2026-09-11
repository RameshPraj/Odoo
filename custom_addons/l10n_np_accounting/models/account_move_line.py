# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang

#: How many counterpart documents to name before summarising. A line matched
#: against fifty documents must not produce an unbounded string in a list cell.
_MAX_NAMED_COUNTERPARTS = 2


class AccountMoveLine(models.Model):
    """Give Community's reconciliation engine a button, and say what it did.

    ``account.move.line.reconcile()`` is public in Community and does the whole
    job -- partial matches, full matches, exchange-difference moves. What
    Community does not ship is any way to *call* it: the drag-and-drop
    reconciliation widget lives in Enterprise ``account_accountant``.

    This adds a header button to the Journal Items list. It is not a
    reimplementation of that widget; it is one button that calls the engine
    already present, after checking the preconditions the engine assumes so the
    user gets a sentence instead of a traceback.

    It also makes the **Matching** column readable. Core stores
    ``matching_number``, a token that is either empty, the
    ``account.full.reconcile`` primary key, ``P<n>`` for a partial match, or
    ``I<x>`` for a line merely *marked* to be reconciled once its moves post
    (``account/models/account_move_line.py:1699-1704``). On a real database that
    renders as bare integers like ``37`` on a few rows and blank everywhere else
    -- and the blanks are the worse half, because "this account can never be
    reconciled" and "this is reconcilable and still owed" look identical.

    ``matching_status`` and ``matching_label`` below turn that into five named
    states. Neither touches ``matching_number``, so the search filters and the
    group-by that reference it keep working unchanged.
    """

    _inherit = 'account.move.line'

    matching_status = fields.Selection(
        selection=[
            ('not_reconcilable', "Not reconcilable"),
            ('open', "Open"),
            ('partial', "Partially matched"),
            ('matched', "Matched"),
            ('pending_post', "Marked, not yet matched"),
        ],
        string="Match state",
        compute='_compute_matching_status',
        store=True,
        index='btree_not_null',
        help="Reconciliation state of this line, derived from the matching data "
             "core already stores. Stored so it can be grouped and filtered.",
    )
    matching_label = fields.Char(
        string="Matching",
        compute='_compute_matching_label',
        help="What this line is matched against, or what is still open. Computed "
             "for display; the underlying token is the Matching # field.",
    )

    # ------------------------------------------------------------------
    #: Account types that carry a real residual even when the account is not
    #: flagged 'Allow Reconciliation'. Core computes residuals for exactly these
    #: (`account/models/account_move_line.py:816`), so calling them
    #: "not reconcilable" would blank out a bank line that genuinely owes money.
    _RESIDUAL_DESPITE_NO_RECONCILE = ('asset_cash', 'liability_credit_card')

    @api.depends('matching_number', 'full_reconcile_id', 'amount_residual',
                 'account_id.reconcile', 'account_id.account_type')
    def _compute_matching_status(self):
        """Five states, from fields core already stores.

        Stored, which is legal here only because every dependency is itself
        stored -- checked rather than assumed. Note the dependency is on
        ``account_id.reconcile`` and **not** on ``is_account_reconcile``: the
        latter is a non-stored related field, and a stored field cannot depend on
        one.

        Order matters, and two orderings here were wrong in the first draft:

        * ``pending_post`` is tested **first**, before ``not_reconcilable``.
          ``_reconcile_marked`` flips ``account.reconcile`` to True itself, but
          only when the moves are posted (``:3166-3169``), so an ``I``-marked line
          legitimately sits on an account whose flag is still False. Testing
          ``not_reconcilable`` first rendered "not reconcilable" on a line that had
          explicitly been queued for matching.
        * ``not_reconcilable`` is **not** ``not account_id.reconcile``. Core
          computes residuals for cash and credit-card accounts regardless of the
          flag (``:816``), so those lines carry a real outstanding amount and
          saying "not reconcilable" would hide it.
        """
        for line in self:
            number = line.matching_number or ''
            account = line.account_id
            carries_residual = (
                account.reconcile
                or account.account_type in self._RESIDUAL_DESPITE_NO_RECONCILE
            )
            if number.startswith('I'):
                line.matching_status = 'pending_post'
            elif not carries_residual:
                line.matching_status = 'not_reconcilable'
            elif line.full_reconcile_id:
                line.matching_status = 'matched'
            elif number.startswith('P'):
                line.matching_status = 'partial'
            else:
                line.matching_status = 'open'

    @api.depends('matching_status', 'amount_residual', 'amount_residual_currency',
                 'is_same_currency', 'reconciled_lines_excluding_exchange_diff_ids')
    def _compute_matching_label(self):
        """The sentence the column shows.

        Deliberately **not stored**: it names counterpart documents, so storing it
        would mean recomputing every line whenever any counterpart's name changed.
        A non-stored computed field still exports, so nothing is lost on XLSX or
        PDF -- verified by execution rather than assumed.

        Two of the choices here are about correctness, not presentation:

        * Counterparts come from ``reconciled_lines_excluding_exchange_diff_ids``,
          not from the raw partials. That field excludes exchange-difference lines
          (``account/models/account_move_line.py:1295-1301``), which would
          otherwise be named as though the exchange entry were the invoice; and it
          is filtered through ``_filtered_access('read')`` (``:1289``), so it
          honours the record rules added for SEC-2. Reading the partials directly
          would be cheaper and would leak counterpart document names across
          companies -- the exact exposure SEC-2 closed.
        * The residual is shown in the line's own currency when that differs from
          the company's, using core's own ``is_same_currency`` switch, so the
          number in this sentence matches the Residual column beside it instead of
          quietly reporting a converted figure.
        """
        for line in self:
            status = line.matching_status
            if status == 'pending_post':
                line.matching_label = _("Marked, not yet matched")
            elif status == 'open':
                line.matching_label = _("Open · %s", line._matching_residual_text())
            elif status == 'matched':
                line.matching_label = _("Matched · %s",
                                        line._matching_counterpart_text())
            elif status == 'partial':
                line.matching_label = _(
                    "Partial · %(counterpart)s, %(residual)s still open",
                    counterpart=line._matching_counterpart_text(),
                    residual=line._matching_residual_text(),
                )
            else:
                # not_reconcilable, and the defensive fallthrough. Empty rather
                # than a dash: the widget draws the dash, so an exported file does
                # not carry punctuation pretending to be data.
                line.matching_label = ''

    def _matching_residual_text(self):
        """The outstanding amount, in the currency the reader is looking at."""
        self.ensure_one()
        if self.is_same_currency:
            amount, currency = self.amount_residual, self.company_currency_id
        else:
            amount, currency = self.amount_residual_currency, self.currency_id
        return formatLang(self.env, abs(amount), currency_obj=currency)

    def _matching_counterpart_text(self):
        """The documents this line is matched against, named and capped."""
        self.ensure_one()
        names = [
            move.name or _("draft entry")
            for move in self.reconciled_lines_excluding_exchange_diff_ids.move_id
        ]
        if not names:
            # Reachable two ways: every counterpart is an exchange-difference
            # line, or a record rule hides them from this user. Saying so beats an
            # empty cell, which would read as "not matched".
            return _("counterpart not visible")
        shown = names[:_MAX_NAMED_COUNTERPARTS]
        remaining = len(names) - len(shown)
        if remaining:
            return _("%(names)s +%(count)s more",
                     names=", ".join(shown), count=remaining)
        return ", ".join(shown)

    # ------------------------------------------------------------------
    def _reconcile_candidates(self):
        """The lines the user actually selected, whichever way the button fired."""
        if self:
            return self
        return self.browse(self.env.context.get('active_ids', []))

    def action_reconcile_selected(self):
        lines = self._reconcile_candidates()
        if len(lines) < 2:
            raise UserError(_(
                "Select at least two journal items to reconcile against each other."
            ))

        not_posted = lines.filtered(lambda aml: aml.parent_state != 'posted')
        if not_posted:
            raise UserError(_(
                "Only posted entries can be reconciled. These are not posted yet:\n%s",
                "\n".join(f"- {aml.move_id.name or _('draft entry')}"
                          for aml in not_posted[:10]),
            ))

        not_reconcilable = lines.filtered(lambda aml: not aml.account_id.reconcile)
        if not_reconcilable:
            raise UserError(_(
                "Reconciliation is only allowed on accounts flagged 'Allow "
                "Reconciliation'. These accounts are not:\n%s\n\n"
                "Set the flag on the account, or exclude those lines.",
                "\n".join(sorted({
                    f"- {aml.account_id.code} {aml.account_id.display_name}"
                    for aml in not_reconcilable
                })),
            ))

        accounts = lines.account_id
        if len(accounts) > 1:
            raise UserError(_(
                "All selected items must sit on one account. You selected %(count)s:\n%(accounts)s",
                count=len(accounts),
                accounts="\n".join(f"- {a.code} {a.display_name}" for a in accounts),
            ))

        already_done = lines.filtered(lambda aml: aml.reconciled)
        if already_done:
            raise UserError(_(
                "%s of the selected items are already fully reconciled. "
                "Filter on 'With residual' to see only what is still open.",
                len(already_done),
            ))

        lines.reconcile()

        matched = len(lines.filtered(lambda aml: aml.reconciled))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Reconciled"),
                'message': _(
                    "%(matched)s of %(total)s items are now fully reconciled. "
                    "Any item still showing a residual was only partly matched.",
                    matched=matched, total=len(lines),
                ),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
