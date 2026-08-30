# -*- coding: utf-8 -*-
"""A report wizard's remembered label limit is personal, not company-wide (SEC-4).

`account_financial_report`'s abstract wizard remembers `label_text_limit` so the
next report defaults to the same value. It does so in `_set_default_wizard_values`
(`wizard/abstract_wizard.py:67-75`):

    self.env["ir.default"].sudo().set(
        self._name, "label_text_limit", self.label_text_limit,
        user_id=False,          # <- every user
        company_id=True,        # <- this company
    )

`user_id=False` means the default applies to **everyone in the company**, and
`sudo()` means the writer's own rights are not consulted. The method runs on every
Export click, from six wizards whose ACLs are open to `base.group_user`. So any
employee who exports a report silently rewrites a setting for every colleague, and
nothing in the UI suggests that is what the field does.

The value itself is cosmetic — it truncates long partner names in a column — so
this is not a privilege-escalation route. It is a shared mutable setting written
by accident, which is the kind of thing that gets noticed as "the reports keep
changing" long after the cause is forgettable.

Overridden here rather than fixed upstream: `VENDORED.md` forbids editing the OCA
modules in place, because the zero-drift property is what keeps the LIC-1 licence
position defensible. `_set_default_wizard_values` is a plain method on an abstract
model, so a local `_inherit` replaces it for all six wizards at once.

The fix keeps the feature and narrows its blast radius to the person who chose the
value: the default is written for `self.env.uid` instead of for everyone. `sudo()`
is kept, because writing one's *own* `ir.default` still requires rights an ordinary
employee does not have, and removing it would turn a shared-state bug into an
AccessError on a working button.
"""
from odoo import models


class AccountFinancialReportAbstractWizard(models.AbstractModel):
    # AbstractModel, matching the vendored declaration. Declaring it Transient
    # here makes Odoo refuse to load at all -- "transforms the abstract model
    # ... into a non-abstract model" -- which is a good error, caught the moment
    # this was first run.
    _inherit = "account_financial_report_abstract_wizard"

    def _set_default_wizard_values(self):
        self.ensure_one()
        self.env["ir.default"].sudo().set(
            self._name,
            "label_text_limit",
            self.label_text_limit,
            user_id=self.env.uid,
            company_id=True,
        )
