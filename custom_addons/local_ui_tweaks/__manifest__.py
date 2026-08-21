# -*- coding: utf-8 -*-
{
    'name': 'Local UI Tweaks',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Deliberate, documented deviations from stock Odoo menus and UI',
    'description': """
A home for small local UI preferences that would otherwise be scattered through
unrelated modules or, worse, edited into core.

Each tweak here changes a record **owned by another module**. That is allowed, and
it is how Odoo is meant to be customised, but it has two consequences worth
knowing before adding to this file:

* the change **persists if this module is uninstalled**, because the record
  belongs to its original module and only its field values were altered. Every
  entry below therefore documents how to revert it by hand.
* it does **not** survive being overwritten if the owning module later ships an
  explicit value for the same field. Fields the owner does not mention are safe,
  since Odoo writes only the fields present in a record.

The same pattern and the same caveat already apply to the `account` group records
rewritten by `l10n_np_accounting` (audit finding UPG-1).

Deliberately NOT auto_install: these are opinions about the interface, not
corrections, and installing opinions automatically is how a database ends up
behaving in ways nobody chose.
""",
    'depends': ['mail'],
    'data': [
        'data/menu_tweaks.xml',
    ],
    'author': 'local',
    'license': 'LGPL-3',
    'installable': True,
}
