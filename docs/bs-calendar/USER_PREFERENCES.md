# User preferences

## The design

```
Calendar System:  Gregorian (AD)  |  Bikram Sambat (BS)
```

**Precedence: user → company → AD.**

| Level | Field | Purpose |
|---|---|---|
| User | `res.users.calendar_system` (`False` = follow company) | The user's own choice |
| Company | `res.company.calendar_system` (default `ad`) | Sensible default for a Nepali entity |
| System | hard-coded `ad` | Nothing configured anywhere |

A second, independent preference controls numerals: `res.company.bs_digits` —
`latin` (`2083-04-29`, default) or `devanagari` (`२०८३-०४-२९`).

**Language and calendar are orthogonal**, as the brief requires. `English + BS` and `Nepali + AD`
are both valid. This falls out of the design: calendar is a sibling of `tz`, not a variant of
`lang` — see [`02_ARCHITECTURE.md`](02_ARCHITECTURE.md) for why modelling it on `res.lang` is not
viable.

## Migration from today's mechanism

BS is currently switched on by a **security group** granted from Settings via `implied_group`, which
adds it to `base.group_user` — so it is effectively **database-wide for all internal users**, and
per-user opt-out requires editing `group_ids` by hand.

Replacing that with a per-user field is a visible behaviour change, so the migration preserves
current behaviour rather than resetting everyone to AD:

```
if the old group is granted to base.group_user:
    company.calendar_system = 'bs'      # everyone keeps seeing BS
    users keep calendar_system = False  # i.e. "follow company"
then retire the group
```

Users who had been individually **removed** from the group are detected and given an explicit
`calendar_system = 'ad'`, so their opt-out survives too.

**This must be tested against a database that actually has the group set** — the migration is
otherwise untested in the only state that matters.

## Server plumbing

All seams verified; every one is a documented override point, no core patch.

| Concern | Seam | Reference |
|---|---|---|
| User may read/write their own preference | override `SELF_READABLE_FIELDS` / `SELF_WRITEABLE_FIELDS` | `res_users.py:175-193` — docstrings explicitly invite it |
| Available in `env.context` server-wide | override `context_get()` | `res_users.py:694-723`; only `lang`/`tz` read today |
| **Cache invalidation** | add to `_get_invalidation_fields()` | `res_users.py:735-740` → triggers `registry.clear_cache()` at `:641-643` |
| Reaches the browser | override `session_info()` | `web/models/ir_http.py:79`; `user_context` already shipped at `:103` |
| UI placement | xpath into `<group name="other_calendar_preferences"/>` | `res_users_views.xml:459` — an anchor placed there for exactly this |
| Client reads it | `session.calendar_system` and `session.bs_digits` | as **top-level** `session_info` keys, via the `nepali_calendar` service |

> The client row previously read `session.user_context.calendar_system`. As built, the two values are
> added as top-level `session_info` keys instead. `user_context` is forwarded verbatim to the server
> as the RPC context, so putting display-only settings there means shipping them back on every call
> for no benefit; and `context_get` already places the calendar in `env.context` server-side, which is
> where server code reads it. The client wants a plain flag, so it gets one.
>
> Company-level settings live beside them: `bs_digits` (numerals) and `bs_report_output` (what printed
> documents show). Both moved into core from `l10n_np_accounting`, where the digit style had been a
> third disagreeing copy.

**Two requirements that are easy to miss and both bite silently:**

1. **`_get_invalidation_fields` is non-negotiable.** `context_get` is `ormcache('self.env.uid')`
   (`res_users.py:695`). Without adding the field, a user changes their preference and nothing
   happens until the server restarts.
2. **Do not put the preference in `lang_params`.** `_get_web_translations_hash` is
   `ormcache('frozenset(modules)', 'lang')` — **no uid** (`base/models/ir_http.py:436`) — and the
   payload is served `Cache-Control: public` (`webclient.py:84-86`). A per-user value there would be
   cross-contaminated between users *and* cached by browsers and CDNs.

After a preference change Odoo's own `preference_save` already returns
`{'type': 'ir.actions.client', 'tag': 'reload_context'}` (`res_users.py:989-993`), so the client
picks up the new calendar without any extra work.

## Why not `res.users.settings`?

`res.users.settings` (`res_users_settings.py`) would also work — it auto-serialises every field to
the browser and provides a write RPC for free. It was rejected as the *primary* home because the
preference is needed **server-side too** (report formatting, the QWeb converters), and
`context_get` is the mechanism that puts it in `env.context` for free. Using both would create two
sources of truth for one setting — the mistake the current digit-style option already makes, where
three places disagree.

## Multi-tenant isolation

Nothing extra required. The preference is an ordinary per-database field on `res.users` /
`res.company`, and every cache touching it is keyed per-user. The one cache that could have leaked
across tenants — the lang-keyed, HTTP-public translations payload — is avoided by design.
