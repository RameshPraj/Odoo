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

> **This is now enforced.** `tools/selftest.py` was refactored from a `print`/`sys.exit` script into
> `check() -> dict`, and `tests/test_conversion_contract.py` asserts on it. The full 46,022-day sweep
> takes **0.9s**, so it runs in its entirety rather than sampled, and it parses the *generated*
> `bs_calendar_data.js` rather than the generator — which is what catches the failure that actually
> happens, a stale checked-in table. A `checked > 45000` assertion guards against the sweep silently
> covering nothing and the other two assertions passing vacuously.

## The two APIs must agree

Python and JavaScript were two "shared" implementations that disagreed. All of the following is now
done and asserted, from both sides, in `tests/test_conversion_contract.py` and
`static/tests/bs_convert.test.js` — deliberately over the *same* dates, so the two files cross-check
one contract rather than testing two things that each happen to pass.

| Concern | Python before | JS before | Decision, as built |
|---|---|---|---|
| Digit default | `np_digits=False` | `npDigits: true` | **Latin by default** on both. Devanagari is opt-in via the company setting — a smaller change to an existing ledger |
| Separators accepted on parse | `-` `/` | `-` `/` `.` whitespace | **All four on both.** Being liberal on input is right; the output format is what must be canonical |
| Failure contract | raises `UserError` | returns `null` | **Both kept, deliberately.** Python raises (server-side a bad date is a bug or a validation error); JS returns `null` (the widget must show a notification, not crash the UI). Documented and asserted rather than unified |
| Weekday names | long — `आइतबार` | short — `आइत` | **Both, everywhere.** `WEEKDAYS_NE_LONG` / `_SHORT` in Python, `bsWeekdayNames({ long })` in JS |
| Range constants | absent; hard-coded in an error string | `BS_MIN_YEAR` / `BS_MAX_YEAR` exported | **Exported from Python too**, and interpolated into the error message |
| Month-name format | `२०८३-भदौ-२४` | `२०८३ भदौ २४` | **Spaces**, matching normal Nepali usage |
| Day padding in month-name form | `%02d` — `भदौ 09` | unpadded — `भदौ 9` | **Padded on both.** Found while writing the tests; it was the last surviving divergence, and it meant a PDF and a list view disagreed about the same record |

**Single source for names — done, but not where the plan put it.** The tables existed three times:
`bs.py`, `bs_calendar_data.js`, and hard-coded *again* inside the generator meant to be producing
them. The plan made the generator the sole author; in practice the generator is a standalone script
run outside an Odoo process, so it cannot import `bs.py` (which imports `odoo.exceptions`).

The names therefore live in a new **`tools/names.py`** that imports nothing at all. `bs.py` imports
it normally; `gen_js_data.py` loads it by path and *emits* it into the JS table. One source, three
consumers, and a test asserting the generated arrays are byte-equal to the Python lists — including
both weekday lengths, which is the specific pair that had drifted.

## Error handling

`month_length()` was the one function that did not wrap library exceptions — it raised a raw
`KeyError` at BS 2101 and a raw `AssertionError` for month 13. That escaped the fiscal-year wizard's
`UserError`-only catch and surfaced as a traceback, **reachable by default** from BS 2097 onward
because the wizard defaults to `current + 4`.

**Fixed and asserted** (`TestRangeContract.test_month_length_out_of_range_raises_user_error`): it now
bound-checks the year and month itself and wraps anything the library throws, like its siblings. The
test asserts `UserError` specifically, not just "raises" — a bare `IndexError` reaching a user is a
server error with a traceback, which is the behaviour being removed.

The wizard's own bound check (BSD-7) is still open; this change means it now fails with a readable
message rather than a traceback, which is a mitigation, not the fix.

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
symbol, acknowledged with `# noqa: SLF001`. It was declared in `external_dependencies` but absent from
`requirements.txt` and unpinned, so a fresh environment could not install the suite at all, and any
upgrade might remove the symbol.

**Both halves are now closed.** `nepali-datetime==1.0.8.5` is pinned in the project-additions block at
the end of `requirements.txt`, and the 46,022-day sweep runs in the suite — so a library upgrade that
changed the table would fail the build rather than silently producing wrong dates in a fiscal year.
`tests/test_requirements.py` also asserts the pin matches the *installed* version (otherwise the sweep
validates a version the deployment never gets) and that `_days_in_month` still exists.

The private symbol remains a private symbol. Pinning makes its removal a deliberate, visible event
instead of a surprise; it does not make the dependency safe.
