# -*- coding: utf-8 -*-
"""Clear the company-wide report defaults the SEC-4 bug already wrote.

Stopping the write is not the same as undoing it. `_set_default_wizard_values` in
`account_financial_report/wizard/abstract_wizard.py:67-75` wrote

    ir.default.set(..., "label_text_limit", value, user_id=False, company_id=True)

on **every Export click**, from six wizards whose ACLs were open to
`base.group_user`. `user_id=False` means "for everyone in this company", so each
export overwrote a setting for every colleague. The override in
`models/abstract_wizard.py` makes new writes personal, but the rows already
written stay in the database and keep applying to everybody.

They are real here, not hypothetical. Measured on the live database before this
migration was written -- four rows, one per report anyone had exported:

    trial.balance.report.wizard          user=None  company=My Company  value=40
    general.ledger.report.wizard         user=None  company=My Company  value=40
    aged.partner.balance.report.wizard   user=None  company=My Company  value=40
    vat.report.wizard                    user=None  company=My Company  value=40

Deleted rather than reassigned to somebody. There is no way to tell whose value
it was -- that information was never recorded, which is the bug -- and inventing
an owner would be worse than losing a preference. With the row gone the field
falls back to its own declared default, and the next person to export sets one
for themselves.

Scoped to `label_text_limit` on the six OCA report wizards. Other `ir.default`
rows with no `user_id` are legitimate company defaults set deliberately from
Settings, and this must not touch them.
"""
import logging

_logger = logging.getLogger(__name__)

#: The wizards that inherit account_financial_report's abstract wizard.
WIZARD_MODELS = (
    "aged.partner.balance.report.wizard",
    "general.ledger.report.wizard",
    "journal.ledger.report.wizard",
    "open.items.report.wizard",
    "trial.balance.report.wizard",
    "vat.report.wizard",
)


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        """
        DELETE FROM ir_default
              USING ir_model_fields AS f
              WHERE ir_default.field_id = f.id
                AND f.name = 'label_text_limit'
                AND f.model = ANY(%s)
                AND ir_default.user_id IS NULL
        """,
        [list(WIZARD_MODELS)],
    )
    if cr.rowcount:
        _logger.info(
            "SEC-4: removed %s company-wide report label-limit default(s); each "
            "user now sets their own on next export.", cr.rowcount)
