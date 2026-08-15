# -*- coding: utf-8 -*-
{
    'name': 'Nepali Calendar (Core)',
    'version': '19.0.1.0.0',
    'summary': 'Bikram Sambat as a platform capability: conversion, preference, widgets, reports',
    'description': """
Nepali Calendar (Core)
======================

Bikram Sambat (BS) support for the whole of Odoo, as a **presentation layer**.

Odoo continues to store canonical Gregorian dates in PostgreSQL. The ORM, domains,
RPC, imports and exports all keep seeing standard Odoo values. BS exists only in
what is displayed and what may be typed.

Calendar preference
-------------------
Each user chooses ``Gregorian (AD)`` or ``Bikram Sambat (BS)`` in Preferences.
Resolution order is **user -> company -> AD**, so a company can default its staff
to BS while an individual overrides.

Calendar and language are independent: ``English + BS`` and ``Nepali + AD`` are
both valid combinations.

Coverage
--------
Rather than enumerating date fields, this module replaces the ``date``,
``datetime`` and ``daterange`` entries in the web client's ``fields``,
``formatters`` and ``parsers`` registries. Odoo renders a date by two routes and
both are covered: a real component (form views, and any column with an explicit
``widget=``) and a plain formatted string (readonly list cells, kanban cards,
column aggregates). Every date field therefore follows the preference, minus a
curated exclusion list (audit columns, cron scheduling, technical timestamps).

One widget needs its own patch: ``remaining_days``, used by the invoice and bill
Due Date column, imports ``formatDate`` statically and so is reachable by neither
registry.

What this does NOT do
---------------------
* Search filters and group-by still use Gregorian period boundaries, so a BS
  month is split. See ``docs/bs-calendar/SEARCH_AND_FILTERS.md``.
* The calendar view grid keeps Gregorian month boundaries.
* Exports stay Gregorian, deliberately, so round-trips remain lossless.

Supported range: BS 1975-01-01 .. 2100-12-30 (AD 1918-04-13 .. 2044-04-12).
Outside it, conversion raises rather than guessing -- the month-length table *is*
the algorithm, and there is no formula to extrapolate.
    """,
    'category': 'Localization',
    'author': 'local',
    'license': 'LGPL-3',
    # `base_setup` for the General Settings form the company defaults live in.
    'depends': ['web', 'base_setup'],
    'external_dependencies': {'python': ['nepali_datetime']},
    'data': [
        'views/bs_calendar_menus.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Order matters: the generated table, then conversion, then consumers.
            'nepali_calendar_core/static/src/bs_calendar_data.js',
            'nepali_calendar_core/static/src/bs_convert.js',
            'nepali_calendar_core/static/src/exclusions.js',
            'nepali_calendar_core/static/src/bs_date_field.js',
            'nepali_calendar_core/static/src/bs_date_field.xml',
            'nepali_calendar_core/static/src/bs_date_field.scss',
            # Registry overrides load last: they replace the native date widgets.
            'nepali_calendar_core/static/src/registry_overrides.js',
            'nepali_calendar_core/static/src/registry_overrides.xml',
            'nepali_calendar_core/static/src/remaining_days_patch.js',
            'nepali_calendar_core/static/src/bs_calendar_action.js',
            'nepali_calendar_core/static/src/bs_calendar_action.xml',
            'nepali_calendar_core/static/src/bs_calendar_action.scss',
        ],
        # Bundled here, but *run* by tests/test_js_unit.py -- declaring them
        # only gets them compiled, never executed.
        'web.assets_unit_tests': [
            'nepali_calendar_core/static/tests/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
