# -*- coding: utf-8 -*-
"""Make the Export fiscal position actually zero-rate an export (ACC-3).

An invoice to a customer carrying the "Export / Zero-rated" position was charged 13%
VAT. Verified before the fix: a 1,000 line came out `taxes=['VAT 13%']`, `tax=130.0`.
The position was applied to the invoice and then did nothing, so exports
over-collected 13% from customers who should not pay it, and the output VAT was
overstated on a return that FIN-1 had only just made capable of reporting anything.

Two things were misconfigured. Only the first turned out to block substitution -- the
finding as written (`BACKLOG.md`, ACC-3: "one cell each") named exactly it, and was
right. The second is fixed here too, for the separate reason given below:

1. `original_tax_ids` was empty on both zero-rated taxes, so nothing declared which
   domestic tax they replace.

2. `res.company.domestic_fiscal_position_id` was unset, so `is_domestic` was False on
   both 13% taxes -- it is computed as `not tax.fiscal_position_ids or
   company.domestic_fiscal_position_id in tax.fiscal_position_ids`
   (`account/models/account_tax.py:331-333`), and both carry the Domestic position, so
   there was nothing to compare against.

   **Correction, recorded rather than quietly dropped.** The plan for this work called
   item 2 a second, independent cause and claimed "substitution is gated on exactly
   that at `account_tax.py:5160`". Both halves of that were wrong, and a negative
   control on a probe database is what settled it: with `original_tax_ids` present but
   `domestic_fiscal_position_id` cleared and `is_domestic` False, an export invoice
   still came out `[0.0]` / `tax=0.0`. Clearing `original_tax_ids` instead brought 13%
   straight back. Item 1 alone is the fix.

   `account_tax.py:5160` sits in `_import_retrieve_tax_from_price_include_exclude`, a
   bill-import tax-matching helper, and the `is_domestic` there belongs to
   `account.fiscal.position` (`partner.py:58`) -- a different model on a different code
   path. Every genuine use of `account.tax.is_domestic` is UI-side: the
   `original_tax_ids` domain (`:110`), the `name_search` "Domestic" filter (`:262`), and
   two list-view filters.

   It is still set here, for a reason worth stating. Without it the `Replaces` field's
   own domain `[('is_domestic', '=', True)]` matches nothing, so an accountant opening
   VAT 0% gets an empty dropdown and cannot maintain -- or even see the shape of -- the
   link this migration writes by ORM, where domains are not enforced. Skipping it would
   leave the fix correct but unmaintainable by hand.

Why this does NOT call try_loading, unlike the FIN-1 migration next door
-----------------------------------------------------------------------
That was the first attempt, and the migration's own assertion caught it failing: the
chart reload left `account_tax_alternatives` empty. The reason is in
`chart_template.py:412-421`, which re-applies `original_tax_ids` only

    if force_create and original_tax_ids and (new_taxes := [
        xml_id for xml_id in original_tax_ids.split(',') if xml_id not in xmlid2tax])

with the comment "Only add tax mappings containing new taxes". `VAT_S_NP_13` already
exists, so it is not in `new_taxes`, and core deliberately declines to touch the
mapping -- it treats substitution links on existing taxes as user-managed. A reload
re-applies repartition tags (which is what FIN-1 needed) and fiscal-position links,
and nothing else.

So the link is written directly here, by xmlid. The CSV change alongside this is not
redundant: on a **fresh** chart adoption the taxes are new, `new_taxes` is non-empty,
and the template is what supplies the mapping. CSV for new databases, this for
existing ones.

**Not retrospective.** Taxes are resolved when an invoice line is created, so any
export already invoiced at 13% stays wrong and needs a credit note. This fixes what
happens next.
"""

#: Zero-rated template id -> the domestic template id it replaces.
SUBSTITUTIONS = (
    ('VAT_S_NP_0', 'VAT_S_NP_13'),
    ('VAT_P_NP_0', 'VAT_P_NP_13'),
)


def migrate(cr, version):
    from odoo import Command, SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = env['res.company'].search([('chart_template', '=', 'np')])
    if not companies:
        return

    for company in companies:
        # Resolved by xmlid, not by name: the names are translatable.
        domestic = env.ref(
            f'account.{company.id}_fiscal_position_np_national',
            raise_if_not_found=False)
        if domestic and not company.domestic_fiscal_position_id:
            company.domestic_fiscal_position_id = domestic

        for zero_rated_id, domestic_id in SUBSTITUTIONS:
            zero_rated = env.ref(f'account.{company.id}_{zero_rated_id}',
                                 raise_if_not_found=False)
            replaces = env.ref(f'account.{company.id}_{domestic_id}',
                               raise_if_not_found=False)
            if zero_rated and replaces:
                zero_rated.original_tax_ids = [Command.link(replaces.id)]

    # Assert both. The first is the fix and its absence is silent -- the invoice simply
    # carries the wrong tax. The second is not required for substitution (see above);
    # it is asserted so the link stays configurable through the UI.
    problems = []
    for company in companies:
        for zero_rated_id, _domestic_id in SUBSTITUTIONS:
            tax = env.ref(f'account.{company.id}_{zero_rated_id}',
                          raise_if_not_found=False)
            if tax and not tax.original_tax_ids:
                problems.append(
                    f"{company.name}: {tax.name} ({tax.type_tax_use}) declares no tax "
                    f"to replace")
        for tax in env['account.tax'].search([
                ('company_id', '=', company.id), ('amount', '=', 13.0)]):
            if not tax.is_domestic:
                problems.append(
                    f"{company.name}: {tax.name} ({tax.type_tax_use}) is not "
                    f"is_domestic, so the Replaces field cannot be edited in the UI")
    if problems:
        raise AssertionError(
            "ACC-3 migration ran but did not reach its postcondition:\n  "
            + "\n  ".join(problems))
