# Date conversion

## Correctness — verified, not assumed

The existing conversion was replayed in full against `nepali_datetime` 1.0.8.5:

| Check | Result |
|---|---|
| **AD→BS for every one of the 46,022 supported days** | **0 mismatches** |
| **BS→AD for every day** | **0 mismatches** |
| Generated JS table vs library, all 1,512 (year, month) pairs | **0 differences** |
| Fiscal-year ranges across 125 BS years | 0 gaps, 0 overlaps, no off-by-one |

`AD → BS → AD == AD` holds for the entire supported range, in both directions.

**Range:** BS 1975-01-01 … 2100-12-30, i.e. AD 1918-04-13 … 2044-04-12. Epoch
`BS_EPOCH_AD = [1918, 4, 13]`. Month lengths are table-driven (29/30/31/32 days) — there is no
formula, so the table *is* the algorithm.

**This guarantee is currently enforced by nothing.** `tools/selftest.py` performs exactly the sweep
above and is imported by no test, referenced only in its own docstring. Wiring it in is the single
cheapest high-value item in this project — the verification already exists and already works.

## The two APIs must agree

Python and JavaScript are today two "shared" implementations that disagree. The central module
reconciles them; these are the decisions:

| Concern | Python today | JS today | **Decision** |
|---|---|---|---|
| Digit default | `np_digits=False` | `npDigits: true` | **Latin by default** on both. Devanagari is opt-in via the company setting — a smaller change to an existing ledger |
| Separators accepted on parse | `-` `/` | `-` `/` `.` whitespace | **Accept all four on both.** Being liberal on input is right; the output format is what must be canonical |
| Failure contract | raises `UserError` | returns `null` | **Keep both, deliberately.** Python raises (server-side a bad date is a bug or a validation error); JS returns `null` (the widget must show a notification, not crash the UI). Documented rather than unified |
| Weekday names | long — `आइतबार` | short — `आइत` | **Both, as separate accessors.** `weekday_short()` / `weekday_long()`. The picker needs short, a report may want long |
| Range constants | absent; hard-coded in an error string | `BS_MIN_YEAR` / `BS_MAX_YEAR` exported | **Export from Python too**, and interpolate them into the error message instead of hard-coding "1975…2100" |
| Month-name format | `२०८३-भदौ-२४` | `२०८३ भदौ २४` | **Spaces**, matching the JS and normal Nepali usage |

**Single source for names.** Month and weekday tables exist three times today —
`bs.py`, `bs_calendar_data.js`, and hard-coded *again* in the generator `gen_js_data.py:96-109`.
That third copy is the root cause of the long/short divergence, because the generator does not derive
names from the library. The generator becomes the only author; Python and JS both consume what it
emits.

## Error handling

`month_length()` is the one function that does not wrap library exceptions — it raises a raw
`KeyError` at BS 2101 and a raw `AssertionError` for month 13. That escapes the fiscal-year wizard's
`UserError`-only catch and surfaces as a traceback, **reachable by default** from BS 2097 onward
because the wizard defaults to `current + 4`. It gets the same wrapping as its siblings.

## Timezone — the rule

```
date      :  stored value IS the date.  No conversion.  Safe.
datetime  :  UTC  →  user tz  →  local AD Y/M/D  →  BS
```

**Never UTC → BS directly.**

This is not hypothetical. Today the widget reads **browser-local** components with no normalisation
at all, and Odoo never assigns `luxon.Settings.defaultZone` in production — so "default" is the
browser OS zone, not `res.users.tz`. A datetime stored `2026-09-08 19:00 UTC` renders:

- **BS 2083-05-24** on a browser set to Asia/Kathmandu (00:45 on the 9th, UTC+05:45)
- **BS 2083-05-23** on a browser set to UTC

A day-boundary error exists for the 5h45m window each day.

It is latent only because every currently-covered field is a `date`. **94 of the 237 business date
fields are `datetime`**, so the global rollout exposes all of them — which is why the fix lands
first.

Server-side the precedent is exact: `Datetime.context_timestamp` (`fields_temporal.py:210-229`)
reads `record.env.tz`. "Today" must come from the same place, not `new Date()` — otherwise the
widget's today-highlight disagrees with the server's `context_today` for part of every day.

## Nepal-specific details

- **Week starts Sunday**, consistently in both implementations.
- **Saturday is the weekly holiday**, not Sunday. The reference calendar gets this right
  (`bs_calendar_action.js:91`); the date-picker popup does not flag weekends at all. Two grids in
  one module currently disagree.
- **Devanagari digits must come from our own code.** Odoo's `NUMBERING_SYSTEMS` table explicitly
  comments out `ne` (Nepali) as having no Intl numbering system
  (`localization_service.js:21-31`), so Odoo leaves us on `latn`. `toNpDigits` already does this
  correctly. Useful precedent: `core/l10n/time.js:5-11` carries a Devanagari digit map for time
  *parsing*.
- No Nepal timezone is anchored anywhere today — grep for `Kathmandu`, `Asia/`, `05:45` across all
  three modules returns zero hits. That absence is the root cause of the two timezone defects above.

## Library dependency

`nepali_datetime` is used for the authoritative table and for `_days_in_month` — a **private**
symbol, acknowledged with `# noqa: SLF001`. It is declared in `external_dependencies` but **absent
from `requirements.txt`** and unpinned, so a fresh environment cannot install the suite at all and
any upgrade may remove the symbol.

Mitigation: pin it in a project-owned requirements file, and let the wired-in selftest be the
detector — if a library upgrade changes the table or removes the symbol, the 46,022-day sweep fails
in CI instead of silently producing wrong dates in a fiscal year.
