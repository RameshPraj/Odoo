# -*- coding: utf-8 -*-
"""Backward-compatibility re-export.

The implementation moved to ``nepali_calendar_core.tools.bs``. This shim exists so
that ``from odoo.addons.l10n_np_bs.tools import bs`` keeps working -- notably in
``l10n_np_fiscal_year``, which is therefore untouched by the move.

Import from ``nepali_calendar_core`` in new code.
"""
# `import *` is deliberate here: the point is to mirror the module's public
# surface without restating it, so the two cannot drift.
from odoo.addons.nepali_calendar_core.tools.bs import *  # noqa: F401,F403
from odoo.addons.nepali_calendar_core.tools.bs import (  # noqa: F401
    BS_MAX_YEAR,
    BS_MIN_YEAR,
    MONTHS_EN,
    MONTHS_NE,
    NP_DIGITS,
    ad_to_bs,
    bs_to_ad,
    format_bs,
    from_np_digits,
    month_length,
    parse_bs,
    to_np_digits,
)

#: Kept under its historical name; core now exposes long and short forms
#: separately, because Python and JS previously carried different ones.
from odoo.addons.nepali_calendar_core.tools.bs import (  # noqa: F401
    WEEKDAYS_NE_LONG as WEEKDAYS_NE,
)
