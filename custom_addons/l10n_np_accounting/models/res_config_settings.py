# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Surface the calendar settings where an accountant looks for them.

Bikram Sambat used to be an accounting feature switched on by a group defined
here. It is now a platform preference owned by ``nepali_calendar_core``:
per-user, resolved user -> company -> AD, and covering every date field rather
than a 20-field allowlist.

Nothing is redefined here. The three fields below already exist on
``res.config.settings`` courtesy of core, so this module only needs to place them
in the Accounting settings page as well as General Settings -- one company field,
two doors. An accountant configuring a Nepali ledger should not have to know that
the calendar lives under General Settings.

The old ``group_l10n_np_bs_accounting_dates`` checkbox and
``l10n_np_bs_digits`` field are gone; ``migrations/19.0.1.1.0/pre-migration.py``
carries their values onto the new fields.
"""
