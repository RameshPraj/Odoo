# -*- coding: utf-8 -*-
"""Re-apply the chart's tax data so VAT repartition lines regain their tax tags.

Finding FIN-1. The VAT return computed every box as zero because no repartition line
carried a tax tag, so `l10n_np_vat_return`'s `_tag_balance` matched no journal item
and returned 0.0 for each box, silently.

The template was never wrong. `data/template/account.tax-np.csv` populates
`repartition_line_ids/tag_ids`, and the eight `account.account.tag` records exist
with the right names, applicability and country. The database was stale, because
Odoo instantiates chart-template data when a company **adopts** a chart, not on
`-u`: the repartition lines still reflected the original scaffold commit, whose tag
column was empty. Nothing short of re-applying the tax model can fix that, which is
why this is a migration and not a data-file edit.

Runs **post**-migration, after the module's own data files have loaded, so the tags
this depends on are certainly present.

Why `try_loading` rather than writing the m2m rows directly
-----------------------------------------------------------
Core is built for exactly this. `try_loading` routes through `_pre_reload_data`,
which for a tax whose template has not materially changed clears every value except
its repartition lines and re-applies only their `tag_ids`
(`account/models/chart_template.py:398-427`). Hand-writing the links would duplicate
a name-to-tag mapping that core already derives from the CSV, and would drift from it.

Rehearsed on a `CREATE DATABASE ... TEMPLATE` copy of a live database before being
run anywhere real. Before: 0 tag links. After: 16, with accounts, taxes, fiscal
positions, journal entries and journal items all unchanged in number, and no tax
renamed `[old]` or duplicated. 16 rather than 24 is correct: the 13% taxes take a
tag on all four lines, while the 0% and Exempt taxes take one on their base lines
only, because a zero-rated supply has no tax amount to report. That mirrors the CSV,
which leaves those cells empty.

**A limit worth knowing.** `account.move.line.tax_tag_ids` is stamped when an entry
is posted. This repairs the taxes, not history: any entry posted while the tags were
missing stays untagged and stays invisible to the VAT return. Re-tagging it means
resetting the entry to draft and posting it again. On the database this was written
for that is moot, because no posted line carried a tax at all.
"""


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = env['res.company'].search([('chart_template', '=', 'np')])
    if not companies:
        return

    for company in companies:
        env['account.chart.template'].with_company(company).try_loading(
            'np', company=company, install_demo=False)

    # Assert the postcondition rather than trusting it: a silent no-op here would
    # leave the VAT return reporting nil, which is the whole defect.
    untagged = env['account.tax.repartition.line'].search_count([
        ('company_id', 'in', companies.ids),
        ('tax_id.amount', '=', 13.0),
        ('tax_id.amount_type', '=', 'percent'),
        ('tag_ids', '=', False),
    ])
    if untagged:
        raise AssertionError(
            f"FIN-1 migration ran but {untagged} repartition line(s) on the 13% taxes "
            f"still carry no tax tag; the VAT return would still compute nil"
        )
