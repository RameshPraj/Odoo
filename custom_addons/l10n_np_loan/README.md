# Loans

A loan register with an amortisation schedule that posts to the ledger.

Enterprise's `account_loans` is licensed **OEEL-1** and cannot be used here, so this is
written from scratch on Community `account` alone.

Deliberately named **`l10n_np_loan`, not `account_loan`**, so that OCA's module of that name
can be installed alongside it without an xmlid clash. If a 19.0 port of OCA `account_loan`
turns out to exist and suit you better, this can be dropped for it — nothing else in the
suite depends on the model names beyond the two menu entries and the Bikram Sambat date
mapping.

## Repayment methods

`NPR 1,200,000 @ 12% over 6 monthly instalments`

| Method | Instalment 1 | Instalment 6 | Total interest |
|---|---|---|---|
| Equal instalment (EMI) | 207,058.04 | 207,058.04 | 42,348.24 |
| Equal principal | 212,000.00 | 202,000.00 | 42,000.00 |
| Interest only | 12,000.00 | 1,212,000.00 | 72,000.00 |

The **final instalment repays whatever principal remains** rather than a recomputed figure.
That is what makes the closing balance land on exactly zero under any method, rate and
rounding, instead of a few paisa either side — a residue nobody can later clear off the
liability account.

The period rate is the nominal annual rate divided evenly by the instalments per year, not
an effective-rate conversion. That is how Nepali bank sanction letters quote it, and matching
the lender's own arithmetic matters more here than compounding purity.

## Entries produced

Drawdown (`Post Drawdown`):

| | Debit | Credit |
|---|---|---|
| Bank / cash | principal | |
| Loan account | | principal |

Each instalment (`Post`, or `Post Due Instalments` for everything now due):

| | Debit | Credit |
|---|---|---|
| Loan account | principal portion | |
| Interest expense | interest portion | |
| Bank / cash | | payment |

Every entry is posted balanced, and the loan moves to **Closed** once the last instalment is
posted. `Outstanding principal` counts **posted** instalments only, so a schedule that exists
but has not been paid never understates the liability.

## Nothing is hard-coded

Rate, term, frequency, method and all four accounts are fields on the loan record. Two loans
from two banks on two rates are simply two records, editable by an accountant without a
developer.

## What this does not do

No penal interest, no moratorium or grace period, no floating rates tied to a published base
rate, no restructuring, no prepayment handling. A rate change must be recorded by closing the
loan and opening a new one.

The schedule cannot be rebuilt once any instalment is posted — that would orphan entries
already in the ledger. Reverse them first, or record the change as a new loan.

## Tests

24 tests. The ones that matter:

- every method closes on **exactly** zero, including at awkward numbers (`9.75%` over 7)
- principal repaid equals principal borrowed, to the currency's precision
- each row is internally consistent and balances chain between rows
- a zero-rate loan does not divide by zero
- an absurd rate where the payment never covers the interest is **refused with a sentence**,
  not left to produce a schedule that grows forever
- entries balance, hit the right accounts, and cannot be posted twice
- `Outstanding` follows posted instalments only
