---
id: ST37
type: Sub-task
summary: "Load stock valuation and fixed asset register with opening WDV"
epic: E11
parent: S23
status: "Blocked"
priority: High
story_points: 3
component: "Accounting"
labels: [migration, stock, assets]
depends_on: [S11]
assignee: ~
due_date: 2027-07-05
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# ST37 · Load stock valuation and fixed asset register with opening WDV

**Sub-task** · High · `Blocked` · 3 pts · Accounting · due 2027-07-05 · FY2084-golive

Opening stock valuation and the asset register including written-down value per depreciation block.

## Acceptance criteria

Given the opening entry, when the asset register is listed, then each asset carries its block, cost and opening WDV, and the total agrees to the control account.

## Depends on

- [`S11`](../../E5-nepal-statutory-vat-tds-compliance/S11-decide-implement-nepal-depreciation-method.md) — Decide and implement Nepal depreciation method

## Source reference

- `NEPAL-ACCOUNTING-BUILD-PLAN.md Phase C1`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
