# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Nepal - VAT Return (IRD)',
    'version': '19.0.1.1.0',   # 1.1.0 = multi-company record rules (SEC-2),
                              # plus company_id on the box and line models
    'countries': ['np'],
    'category': 'Accounting/Localizations',
    'summary': 'IRD VAT return driven by a versioned, configurable form definition',
    'description': """
Nepal - VAT Return (IRD)
========================

Produces the IRD VAT return from a **form definition held as data**, not code.

    l10n_np.vat.return.form   one version of the statutory form
      +-- l10n_np.vat.return.box   one box, mapped to tax tags or a formula

Box amounts are summed from tax tags on posted journal items, so every figure on
the return traces back to the ledger and can be drilled into during an audit.

.. important::

   **No form definition ships with this module, deliberately.**

   The IRD sets the return layout, its box numbers, and which figures belong in
   each box. Inventing that would produce a plausible-looking but wrong filing.
   An authorised user defines it under Accounting > Configuration > VAT Return
   Forms.

   Forms are **versioned** with in-force dates: when the IRD revises the form, a
   new version is added and returns already filed keep rendering against the
   version that applied at the time.
""",
    'depends': ['l10n_np'],
    'data': [
        'security/ir.model.access.csv',
        'security/l10n_np_vat_return_rules.xml',
        'views/vat_return_views.xml',
    ],
    'author': 'local',
    'license': 'LGPL-3',
    'installable': True,
}
