# Nepal — TDS (Withholding Tax)

**This module ships with an EMPTY rate table. That is deliberate.**

Nepali TDS rates, thresholds and exemptions are set by the Income Tax Act and amended by
Finance Acts. They are not knowledge that belongs in source code, and a guessed rate
produces wrong filings. The module supplies the mechanism; your accountant supplies the
numbers.

## What is built and verified

| Model | Purpose |
|---|---|
| `l10n_np.tds.category` | Rate schedule with effective-from/to dates |
| `l10n_np.tds.certificate` | Certificate issued to a payee, populated from posted withholding lines |
| `l10n_np.tds.certificate.line` | Individual withholding entries |
| `l10n_np.tds.return` | Periodic aggregation for filing |

Deduction itself is **not** reimplemented — it reuses `account.withholding.line` from
Odoo's own `l10n_account_withholding_tax`.

### The rate-versioning guarantee (tested)

```
RENT  10%  effective 2025-07-17 .. 2026-07-16
RENT  12%  effective 2026-07-17 .. (open)

_rate_for_date('RENT', 2026-01-15) -> 10%   ← a closed period keeps its old rate
_rate_for_date('RENT', 2026-09-15) -> 12%
```

**A Finance Act change is a new record, not an edit.** Overlapping date ranges for the
same code are rejected at write time, so you cannot accidentally create ambiguity.

12 tests pass, including: ships with no rates · missing rate raises a clear error ·
effective-date lookup · overlap rejected · adjacent ranges allowed · negative and >100%
rates rejected · XML well-formedness.

## What an accountant must supply

| # | Item | Where it goes |
|---|---|---|
| 1 | TDS categories: nature of payment, code | `l10n_np.tds.category` |
| 2 | Rate for each category, and its effective dates | same |
| 3 | Annual threshold per category, if any | same |
| 4 | Which liability account each category credits | same |
| 5 | Legal reference (Act/section) for audit | same, `legal_reference` |
| 6 | **The statutory certificate layout** | not yet built — see below |
| 7 | TDS return format and filing periodicity | `l10n_np.tds.return` reporting |

Enter items 1–5 at **Accounting → Configuration → TDS Categories**. No developer needed,
now or when a rate changes.

## Not yet built

- **Certificate print layout.** The model and data are complete; the statutory PDF format
  is not, because the mandatory fields and layout must be confirmed. Once supplied it is a
  QWeb template over `l10n_np.tds.certificate`.
- **TDS return export** in whatever file format the IRD accepts.
- **Threshold enforcement.** The `threshold` field is stored but not yet applied
  automatically at payment time; confirm whether it is cumulative per payee per fiscal
  year before wiring it, because that detail changes the implementation.

## Design rules for anyone extending this

1. **Never hardcode a rate.** Always `_rate_for_date(code, date, company)`.
2. **Never edit a rate in place** to reflect a change in law. Close the old record with an
   effective-to date and create a new one, or past returns will silently change.
3. Certificates read from the ledger, never recompute. A certificate that disagrees with
   the accounts is worse than no certificate.
4. `models.Constraint` — not the legacy `_sql_constraints` list, which Odoo 19 ignores
   silently. This module was written with the list first and the check never reached the
   database; a test caught it.
