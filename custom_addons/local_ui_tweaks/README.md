# Local UI Tweaks

Small, deliberate deviations from stock Odoo's interface, kept in one place so they
are findable. If the UI behaves differently from a vanilla Odoo 19 and it is not a
localisation or accounting concern, look here first.

## Why a separate module

Each tweak writes to a record **owned by another module**. Scattering those through
`l10n_np_accounting` or `nepali_calendar_core` would bury interface opinions inside
modules about Nepali accounting and Bikram Sambat dates, where nobody would think to
look for them. One named module is the honest structure, and it makes "why is my menu
different" answerable in one place.

Not `auto_install`. These are opinions about the interface, not corrections, and
installing opinions automatically is how a database ends up behaving in ways nobody
chose.

## The tweaks

### Discuss: hide the child menu that repeats the app name

Stock Odoo 19 ships **two** menus called "Discuss", both pointing at the same action
`mail.action_discuss` (`odoo/addons/mail/views/mail_menus.xml`, the root at line 3 and
its first child at line 11). Opening the app shows "Discuss" as the app and "Discuss"
again as a menu entry leading where you already are.

The child is set inactive. Safe because the **root** carries the same action, so the
tile still opens Discuss; Channels, Configuration and Technical are untouched.

**To revert:** uninstalling this module does **not** restore it — the record belongs to
`mail` and only its field value was changed. Either flip Active back on in Settings →
Technical → User Interface → Menu Items, or:

```python
env.ref('mail.main_menu_discuss').active = True
```

## Two properties of this approach, worth knowing before adding a tweak

**It persists past uninstall.** The record belongs to its original module; only field
values changed. So every tweak here documents its own manual revert. The same is true
of the `account` group records rewritten by `l10n_np_accounting` — audit finding
**UPG-1**, same mechanism, same caveat.

**It survives a core upgrade only where the owner is silent.** Odoo writes only the
fields a record actually lists, so a field the owning module never mentions is safe.
The stock Discuss menuitem does not specify `active`, so `-u mail` leaves this tweak
alone. A tweak to a field the owner *does* set would be reverted by any upgrade, and
would need a different approach.

## Tests

`tests/test_menu_tweaks.py` asserts through `load_menus`, never `search` —
`ir.ui.menu.search` does not filter the way the client does, and a search-based test
reports menus that will never be drawn. That is exactly how SEC-12 got through a suite
written to catch menu-visibility bugs.

It checks four things: only one Discuss is delivered; the duplicate is *hidden* rather
than deleted, so it stays revertible; the app root still has an action, so the tile is
not a dead end; and Channels and Configuration are still there.
