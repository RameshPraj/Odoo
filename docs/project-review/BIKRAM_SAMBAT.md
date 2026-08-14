# Bikram Sambat

Findings by ID in [`BACKLOG.md`](BACKLOG.md).

## Verdict

**The mathematics is flawless. The periphery is not.**

Every one of the 46,022 supported days was replayed in both directions against the reference
library with **zero divergence**, and the fiscal-year arithmetic is exact and contiguous across
125 Bikram Sambat years. That is a genuinely strong result and it should be said first.

The risk is entirely in what surrounds the conversion: a verification script nobody runs, an
unqualified `datetime` claim with no timezone anchoring, a raw exception at the top of the
supported range, and Gregorian search buckets that split every BS month.

## Conversion correctness — proven, not asserted

Three independent comparisons were executed against `nepali_datetime` 1.0.8.5:

| Check | Result |
|---|---|
| Generated JS table vs the library's `calendar_bs.csv` (126 years × 12 months) | **0 differences** |
| JS table vs `_days_in_month(y, m)` for all 1,512 pairs | **0 differences** |
| **AD→BS for every day**, 1918-04-13 … 2044-04-12 (46,022 days) | **0 mismatches** |
| **BS→AD for every day** (46,022) | **0 mismatches** |

Epoch is consistent (`BS_EPOCH_AD = [1918,4,13]`, `bs_calendar_data.js:15`). Supported range is
BS 1975–2100. All four month lengths occur in the table (29 × 244, 30 × 559, 31 × 512, 32 × 197)
and both implementations handle every one.

Boundary behaviour is **symmetric** between Python and JavaScript: below the range, above it,
month 13, day 33 and BS 2100-12-31 all raise or return an error consistently on both sides.

**The generation pipeline is sound in principle** — `gen_js_data.py` reads the library's own CSV,
so there is one source of truth. The problem is that nothing enforces it.

## BS-1 (P1) — the safety claim is enforced by a script nobody runs

`l10n_np_bs/tools/selftest.py` performs exactly the 46,022-day sweep above. It is:

- not imported by `tests/__init__.py` (which imports only `test_calendar_ui`)
- not called by any test
- referenced nowhere in code — only in its own docstring, the manifest prose, and these documents
- and `l10n_np_bs/__init__.py` is empty

The manifest states: *"generates the JavaScript copy from that same CSV, so the Python and JS
sides can never drift apart."* That claim is true of the *generator* and false of the *repository*
— bumping `nepali_datetime`, or hand-editing the file marked "DO NOT EDIT BY HAND", would not be
caught by anything.

**This is the cheapest high-value fix in the entire audit: wire `selftest.py` into the test
suite.** The verification already exists and already works.

## BS-2 (P1) — `datetime` is declared supported with zero timezone handling

`bs_date_field.js:205` declares `supportedTypes: ["date", "datetime"]`.

The trace: `get value()` (`:44-46`) returns the record value raw; for a Datetime that value came
from `deserializeDateTime`, which does `.setZone(options?.tz || "default")`
(`web/static/src/core/l10n/dates.js:709-715`). Odoo **never assigns
`luxon.Settings.defaultZone` in production** — the only writes are in test files — so "default"
is the **browser OS zone**, not `res.users.tz`. Then `:55` calls
`adToBs(v.year, v.month, v.day)` on those local components.

There is **no `setZone`, `toUTC` or `toLocal` anywhere** in `bs_date_field.js`, `bs_convert.js`
or `bs_calendar_action.js`.

**Concretely:** a datetime stored `2026-09-08 19:00:00` UTC renders as **BS 2083-05-24** on a
browser set to Asia/Kathmandu (00:45 on the 9th) and **BS 2083-05-23** on a browser set to UTC.
A day-boundary error exists for the 5h45m window each day.

**Currently latent (BS-2 note).** Every field in `_BS_DATE_FIELDS` was verified at source to be a
`fields.Date` — no Datetime reaches the widget today. For Date fields the path is safe, because
`deserializeDate` parses at midnight in the default zone and `.year/.month/.day` are exactly the
stored date. But `supportedTypes` explicitly invites a Datetime, and the day it arrives the error
is silent.

**Nuance worth stating:** this is *Odoo-consistent* — the stock `DateTimeField` shows the same
day. The defect is that a module whose entire purpose is the Nepali calendar inherits Odoo's
browser-timezone assumption instead of anchoring to Asia/Kathmandu, and then advertises datetime
support as though it were solved.

Related: **BS-6** — "today" comes from the raw browser clock (`new Date()`, `:127-130`), not
`res.users.tz`, so the widget's today-highlight can disagree with the server's `context_today`
for part of each day. **BS-18** — grep for `Kathmandu`, `Asia/` or `05:45` across all three
modules returns **zero hits**. Nothing is anchored anywhere; that is the root cause of both.

## Storage vs display — this part is right

**BS is genuinely presentation-only, and that is the correct design.**

`bs_accounting_dates.py:55-82` only sets `widget` and `options` XML attributes; nothing converts
stored values. The widget writes only a luxon DateTime or `false` (`bs_date_field.js:89,96,191`),
and `onInputChange` parses to a triple and converts through `bsToAd` *before* any write — so **no
BS string can reach the ORM** (BS: verified, clean). A test reads the raw column back via SQL to
prove it.

The arch cache key is correct and necessary. Core's key is
`(view_id, view_type, mobile, lang, *_view_ref)` (`ir_ui_view.py:3082-3084`) — no uid, no
company — and `_get_view` is called from inside an ormcached wrapper. Without the override, the
first user to open a form would fix the rendering for everyone else. Both leak directions are
tested. Cost is 4× arch-cache entries per view, which is acceptable.

## BS-3 (P2) — the most consequential functional gap

Search views are deliberately excluded from patching (`bs_accounting_dates.py:57-60`), and that
exclusion is asserted by a test. The consequence is not a bug so much as an unfinished feature:

`account.view_account_move_filter` declares `<filter name="date" date="date"/>`
(`account_move_views.xml:365`), so Odoo generates **Gregorian** Month/Quarter/Year buckets. A BS
user selecting "August 2026" gets 2026-08-01 … 08-31 — **BS Bhadra 16 to Ashoj 15, straddling two
BS months**. The same applies to `group_by` on `date:month`, which is a PostgreSQL `date_trunc`
on the Gregorian column.

There is **no BS-aware period filter or group-by anywhere**, and no `_read_group` or `search`
override in any of the three modules.

**For a Nepali ledger this is the point where the localisation stops.** The dates display in BS
right up until you try to report by period — which is most of what an accountant does.

Related: **BS-8** — only `form` and `list` views are patched, so kanban, calendar, graph and **all
PDF reports** stay Gregorian. A user with the setting on sees BS on the invoice form and AD on the
printed invoice. **BS export/RPC** also emit Gregorian, consistent with the design but a
user-visible surprise that the settings help text should state.

## Fiscal year — arithmetic exact, error handling not

**BS-19 (verified):** `SHRAWAN = 4`, `ASHAR = 3` are correct for the table's Baisakh=1 indexing.
`_fiscal_year_range` was recomputed for **all 125 fiscal years BS 1975–2099**: zero gaps, zero
overlaps, every year starting exactly the day after the previous ended, and no off-by-one at
boundaries. Leap handling is right — 2086 correctly yields 366 days where 2082 and 2084 yield 365.

**BS-4 (P2)** is the flaw. `month_length()` (`bs.py:121-124`) is the **one** Python entry point
with no error wrapping — its siblings `ad_to_bs` and `bs_to_ad` both convert exceptions to
`UserError`. Measured behaviour: `_days_in_month(2101, 1)` raises a raw `KeyError`;
`_days_in_month(2083, 13)` raises a raw `AssertionError`.

`_fiscal_year_range(2100)` calls `month_length(2101, 3)` and therefore raises `KeyError: 2101`.
The wizard's `_onchange_preview` catches only `UserError`, so it escapes as a traceback rather
than an in-form message. **Reachable today** by typing 2100, and reachable *by default* from BS
2097 onward because `bs_year_to` defaults to `_default_bs_year() + 4`.

**BS-14 (P3)** is a design contradiction worth noting: `generate_np_fiscal_year.py:108-113` writes
`fiscalyear_last_day`/`fiscalyear_last_month` on the company from the **last generated year
only** — while the module's own test `test_end_date_is_not_fixed` and its manifest exist precisely
to assert that a fixed pair *cannot* express Nepal's variable 15/16/17-July year-end. Any code
path falling back to that pair is silently wrong by up to two days.

**BS-15 (P3):** the "Replace existing" option calls `overlapping.unlink()` filtered only on
company and date overlap — no name filter, no confirmation. Hand-made fiscal years are destroyed.

## Testing

**BS-1** above is the headline. Beyond it:

- **TST-4 / BS:** there are **no JavaScript tests at all**. `static/tests/` is declared in the
  manifest and is an **empty, untracked directory** — so it does not even exist on a fresh clone.
  Every finding in the boundary, timezone and search sections lives in untested JS.
- **Python coverage is thin where the risk is.** The suite asserts 3 known dates, a 97-day-stride
  round trip (≈301 of 46,022 days), Devanagari formatting, and one low-side range raise. Not
  tested: the **upper** range end, `month_length()` at all (the exact function behind BS-4),
  explicit 29/30/31/32-day boundaries, invalid `parse_bs` input, and **anything timezone-related**.
- The browser test asserts only that a grid of >20 cells rendered. It never checks a date value.
- **BS-16:** the generator's own guard probes 5 dates — enough to catch a wrong epoch, not enough
  to catch a single wrong month length.

## Recommended sequence

1. **BS-1** — wire `selftest.py` into the suite. **S.** Highest value per unit effort in the audit.
2. **BS-4** — wrap `month_length()`; bound-check the fiscal-year wizard. **XS.**
3. **BS-2** — either drop `"datetime"` from `supportedTypes` or anchor to `res.users.tz`. **S.**
4. **BS-6 / BS-18** — derive "today" from the user timezone; anchor Asia/Kathmandu once, centrally. **S.**
5. **BS-5** — adopt `useInputField` so the DOM cannot diverge from the record. **S.**
6. **BS-7** — check `_fields[name].type` before patching. **XS.**
7. **BS-3** — a BS-aware period filter and group-by. **L**, and the one that decides whether this
   is a Nepali accounting system or a Gregorian one with Nepali date labels.
