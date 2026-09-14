---
id: S28
type: Story
summary: "Model book versus tax depreciation and deferred tax"
epic: E4
parent: ~
status: "Blocked"
priority: High
story_points: 8
component: "Accounting"
labels: [accounting, depreciation, deferred-tax, blocked-ca]
depends_on: [S11]
assignee: ~
due_date: 2027-04-26
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S28 · Model book versus tax depreciation and deferred tax

**Story** · High · `Blocked` · 8 pts · Accounting · due 2027-04-26 · FY2084-golive

NFRS book depreciation and Income Tax Act Schedule 2 pooled depreciation diverge, creating deferred tax that nothing currently computes.

## Acceptance criteria

Given a fiscal year with both book and tax depreciation, when the deferred tax computation runs, then the movement reconciles to the temporary difference and ties to the CA manual computation.

## Depends on

- [`S11`](../E5-nepal-statutory-vat-tds-compliance/S11-decide-implement-nepal-depreciation-method.md) — Decide and implement Nepal depreciation method

## Source reference

- `NEPAL-ACCOUNTING-BUILD-PLAN.md Phase C1`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
