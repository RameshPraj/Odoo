# -*- coding: utf-8 -*-
"""Carry the "Bikram Sambat accounting dates" group over to the calendar preference.

Bikram Sambat used to be switched on by a security group that a Settings checkbox
granted to ``base.group_user``. It is now a per-user preference resolved
user -> company -> AD, provided by ``nepali_calendar_core`` and covering every date
field in Odoo rather than a 20-field allowlist.

Without this script, a database that had the checkbox ticked would silently revert
to Gregorian on upgrade -- the setting would be gone and nothing would replace it.
So: **if the group was granted, the company default becomes BS.** Nobody's screen
changes.

Runs **pre**-migration, before the module's data files are reloaded, because it
reads the old group and the old company column while they are still present and
untouched.

A note on what this deliberately does NOT attempt
-------------------------------------------------
The plan called for detecting users who had been individually *removed* from the
group and giving them an explicit ``calendar_system = 'ad'``. That was based on a
misreading: the group was granted via ``implied_group`` on ``base.group_user``, and
``has_group`` returns True for an implied group regardless of direct membership.
An individual opt-out was therefore never actually possible under the old
mechanism, so there is no such state in any database to migrate. Writing code to
find it would have looked thorough and done nothing.

The new mechanism *does* support per-user opt-out -- that is one of the reasons for
the change -- but nobody can have used it yet.
"""
import logging

_logger = logging.getLogger(__name__)

OLD_GROUP = ('l10n_np_accounting', 'group_bs_accounting_dates')


def _column_exists(cr, table, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return bool(cr.fetchone())


def _old_group_id(cr):
    cr.execute("""
        SELECT res_id FROM ir_model_data
         WHERE module = %s AND name = %s AND model = 'res.groups'
    """, OLD_GROUP)
    row = cr.fetchone()
    return row[0] if row else None


def _group_was_granted(cr, group_id):
    """True when base.group_user implied the BS group, i.e. the checkbox was on."""
    cr.execute("""
        SELECT 1
          FROM res_groups_implied_rel r
          JOIN ir_model_data d
            ON d.res_id = r.gid AND d.model = 'res.groups'
           AND d.module = 'base' AND d.name = 'group_user'
         WHERE r.hid = %s
    """, (group_id,))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        # Fresh install: there is no old state, and writing a company default
        # would turn BS on for someone who never asked for it.
        return

    if not _column_exists(cr, 'res_company', 'calendar_system'):
        # nepali_calendar_core has not created its column yet. Its models load
        # before this module's, but a hand-driven upgrade order can still get
        # here first; skipping is safe because the default is AD either way.
        _logger.warning(
            "res_company.calendar_system is absent, so the Bikram Sambat "
            "preference cannot be migrated. Re-run with -u "
            "nepali_calendar_core,l10n_np_accounting."
        )
        return

    group_id = _old_group_id(cr)
    if not group_id:
        _logger.info("no legacy Bikram Sambat group found; nothing to migrate")
        return

    if _group_was_granted(cr, group_id):
        cr.execute("UPDATE res_company SET calendar_system = 'bs'")
        _logger.info(
            "Bikram Sambat was enabled via the legacy group; every company "
            "default is now 'bs' so no user's dates change. Individuals can "
            "override this in Preferences."
        )
    else:
        _logger.info(
            "the legacy Bikram Sambat group was not granted; leaving the "
            "company default as Gregorian"
        )

    # Carry the digit style across. Same values, new owner: it moved to
    # nepali_calendar_core so that reports and the widget read one field instead
    # of the three disagreeing copies there were before.
    if _column_exists(cr, 'res_company', 'l10n_np_bs_digits') and \
            _column_exists(cr, 'res_company', 'bs_digits'):
        cr.execute("""
            UPDATE res_company
               SET bs_digits = l10n_np_bs_digits
             WHERE l10n_np_bs_digits IS NOT NULL
               AND l10n_np_bs_digits <> bs_digits
        """)
        if cr.rowcount:
            _logger.info("carried the digit style across for %s company(ies)",
                         cr.rowcount)
