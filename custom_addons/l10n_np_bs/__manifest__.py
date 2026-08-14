# -*- coding: utf-8 -*-
{
    'name': 'Nepali Calendar (Bikram Sambat) - compatibility shim',
    'version': '19.0.2.0.0',
    'summary': 'Backward-compatibility shim; the implementation now lives in nepali_calendar_core',
    'description': """
Compatibility shim
==================

The Bikram Sambat implementation moved to **nepali_calendar_core**, where it is a
platform capability rather than an accounting add-on: a per-user calendar
preference, global date-field coverage, timezone-correct datetimes, and BS on
printed documents.

This module remains only so that existing code importing
``odoo.addons.l10n_np_bs.tools.bs`` keeps working. It re-exports the same names.
New code should import from ``nepali_calendar_core``.

It can be uninstalled once no addon imports the old path.
    """,
    'category': 'Localization',
    'author': 'local',
    'license': 'LGPL-3',
    'depends': ['nepali_calendar_core'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
