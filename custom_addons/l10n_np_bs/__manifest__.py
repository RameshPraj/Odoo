# -*- coding: utf-8 -*-
{
    'name': 'Nepali Calendar (Bikram Sambat)',
    'version': '19.0.1.0.0',
    'summary': 'Bikram Sambat date widget and AD/BS conversion',
    'description': """
Nepali Calendar (Bikram Sambat)
===============================

Adds a ``bs_date`` field widget that displays and accepts dates in Bikram
Sambat while storing plain Gregorian dates in PostgreSQL::

    <field name="birthday" widget="bs_date"/>

Storage is unchanged -- every ORM domain, grouping and report keeps working on
the Gregorian value. BS exists only in the presentation layer.

Calendar data
-------------
Bikram Sambat month lengths vary between 29 and 32 days and are not derivable
by formula; they come from published astronomical tables. This module takes its
table from the ``nepali-datetime`` package and generates the JavaScript copy
from that same CSV, so the Python and JS sides can never drift apart.

Regenerate the JS table with::

    venv\\Scripts\\python.exe custom_addons/l10n_np_bs/tools/gen_js_data.py

Supported range: BS 1975-01-01 .. 2100-12-30 (about 1918-04-13 .. 2043 AD).
Dates outside it raise instead of guessing.
    """,
    'category': 'Localization',
    'author': 'local',
    'license': 'LGPL-3',
    'depends': ['web'],
    'external_dependencies': {'python': ['nepali_datetime']},
    'data': [],
    'assets': {
        'web.assets_backend': [
            'l10n_np_bs/static/src/bs_calendar_data.js',
            'l10n_np_bs/static/src/bs_convert.js',
            'l10n_np_bs/static/src/bs_date_field.js',
            'l10n_np_bs/static/src/bs_date_field.xml',
            'l10n_np_bs/static/src/bs_date_field.scss',
        ],
        'web.assets_unit_tests': [
            'l10n_np_bs/static/tests/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
