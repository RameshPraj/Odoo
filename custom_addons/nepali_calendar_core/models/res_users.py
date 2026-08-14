# -*- coding: utf-8 -*-
"""The calendar preference, and the plumbing that carries it.

`calendar_system` is a per-user **presentation** axis, deliberately shaped like
`tz` rather than like `lang`:

* it is per-user and independent of translation, so ``English + BS`` and
  ``Nepali + AD`` are both usable;
* it never changes what is stored;
* it rides in ``env.context`` so server-side consumers (report formatting, the
  QWeb converters) can read it without a query.

Modelling it on ``res.lang`` was rejected: ``date_format`` is a Selection of nine
Gregorian patterns, Babel has no calendar parameter, and ``lang`` also selects the
translation and asset bundles.
"""
from odoo import api, fields, models
from odoo.tools import frozendict

from .res_company import CALENDAR_SELECTION

#: Context key carrying the resolved calendar. Read by the QWeb converters and by
#: anything server-side that formats a date for a human.
CONTEXT_KEY = 'calendar_system'


class ResUsers(models.Model):
    _inherit = 'res.users'

    calendar_system = fields.Selection(
        CALENDAR_SELECTION,
        string="Calendar System",
        help="Calendar used to show and enter dates. Leave empty to follow the "
             "company default.\n\n"
             "Dates are always stored as Gregorian, so changing this affects only "
             "what you see and type -- never the underlying records, reports "
             "totals, or data exports.",
    )

    # -- self-service preference -------------------------------------------
    # Both are properties in Odoo 19 and their docstrings explicitly invite this
    # override. Without the writeable entry a non-admin cannot set their own
    # calendar; without the readable entry the field does not render on the
    # Preferences form.

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['calendar_system']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['calendar_system']

    @api.model
    def _get_invalidation_fields(self):
        """Make a preference change take effect on the next request.

        `context_get` is ``ormcache('self.env.uid')``. Without adding the field
        here, a user changes their calendar, the write succeeds, and nothing
        happens until the server restarts -- a silent failure, so this is not
        optional.
        """
        return super()._get_invalidation_fields() | {'calendar_system'}

    @api.model
    def context_get(self):
        """Carry the resolved calendar in ``env.context``.

        Core reads only ``lang`` and ``tz`` here; adding a key means every
        server-side consumer gets it for free, exactly as ``tz`` does.
        """
        context = super().context_get()
        if not context:
            # No user found -- core returns an empty frozendict; respect that.
            return context
        return frozendict(dict(context, **{CONTEXT_KEY: self._resolve_calendar_system()}))

    # -- resolution --------------------------------------------------------

    @api.model
    def _resolve_calendar_system(self, user=None):
        """user preference -> company default -> 'ad'.

        One helper, called once per request. The point is that no business model
        anywhere needs an ``if user.bs_enabled`` branch.
        """
        user = user or self.env.user
        # sudo(): a user must be able to resolve their own calendar even when the
        # company record is not otherwise readable to them. Only these two
        # presentation fields are touched, and the result grants no data access.
        user_su = user.sudo()
        return user_su.calendar_system or user_su.company_id.calendar_system or 'ad'

    @api.model
    def _calendar_is_bs(self):
        """True when the current user should see Bikram Sambat."""
        return self.env.context.get(CONTEXT_KEY) == 'bs' or (
            CONTEXT_KEY not in self.env.context
            and self._resolve_calendar_system() == 'bs'
        )
