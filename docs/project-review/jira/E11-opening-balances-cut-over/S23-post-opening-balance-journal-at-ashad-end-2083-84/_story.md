---
id: S23
type: Story
summary: "Post opening balance journal at Ashad end 2083/84"
epic: E11
parent: ~
status: "Blocked"
priority: Highest
story_points: 5
component: "Accounting"
labels: [migration, opening-balance]
depends_on: [S22]
assignee: ~
due_date: 2027-07-05
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S23 · Post opening balance journal at Ashad end 2083/84

**Story** · Highest · `Blocked` · 5 pts · Accounting · due 2027-07-05 · FY2084-golive

Build and post the opening entry as at 16 July 2027 with full sub-ledger detail.

## Acceptance criteria

Given the mapped trial balance, when the opening journal is posted, then the resulting balance sheet equals the signed closing position and the entry balances.

## Children

- [`ST36`](./ST36-load-debtor-creditor-sub-ledger-detail.md) · Sub-task · `Blocked` · Load debtor and creditor sub-ledger detail
- [`ST37`](./ST37-load-stock-valuation-fixed-asset-register-opening-wdv.md) · Sub-task · `Blocked` · Load stock valuation and fixed asset register with opening WDV

## Depends on

- [`S22`](../S22-map-spreadsheet-trial-balance-signed-chart.md) — Map spreadsheet trial balance to the signed chart

## Source reference

- `docs/project-review/ACCOUNTING_NEPAL.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
