# -*- coding: utf-8 -*-
"""Make Aged Partner Balance render at all.

The report is unreachable from the UI. Its wizard passes `date_at` as a
`datetime.date` (`aged_partner_balance_wizard.py:137`) while the report immediately
does `datetime.strptime(date_at, "%Y-%m-%d")` (`aged_partner_balance.py:419`), which
requires a string. Pressing Export HTML, PDF or XLSX raises:

    TypeError: strptime() argument 1 must be str, not datetime.date

Verified by calling `button_export_html()` and rendering the action it returns, which
is exactly what the web client does. Tracked as FIN-3.

Why the fix is here and not on the wizard
-----------------------------------------
Coercing the wizard's output was the first attempt and it broke two of the vendored
module's own tests, which do this:

    data.update({"date_at": data["date_at"].strftime(DEFAULT_SERVER_DATE_FORMAT)})
    -- tests/test_aged_partner_balance.py:63 and :98

That line is the whole story. The authors knew the report needs a string, and
converted it *in the test* rather than in the wizard — so the suite passes, the UI
does not, and the defect is invisible from inside the tests. Anything that changes
what the wizard returns therefore breaks those tests for no gain.

So the coercion belongs at the point of consumption, which is also where the same
module already does it: `general_ledger.py:793` guards with
`if isinstance(date_to, str)`. This override applies that established pattern to the
one report that omitted it, and accepts either type.

Not edited in place: `account_financial_report` is AGPL-3 and
`custom_addons/VENDORED.md` forbids it. An upstream fix supersedes this harmlessly,
since normalising an already-correct string is a no-op.
"""
from odoo import api, fields, models


class AgedPartnerBalanceReport(models.AbstractModel):
    _inherit = "report.account_financial_report.aged_partner_balance"

    @api.model
    def _get_report_values(self, docids, data=None):
        if data:
            data = dict(data)
            for key in ("date_at", "date_from"):
                value = data.get(key)
                # Only convert real date values. `date_from` is legitimately False
                # here, and converting unconditionally would make it the string
                # "None" -- which is truthy, so every `if date_from:` downstream
                # would take the wrong branch.
                if value and not isinstance(value, str):
                    data[key] = fields.Date.to_string(value)
        return super()._get_report_values(docids, data=data)
