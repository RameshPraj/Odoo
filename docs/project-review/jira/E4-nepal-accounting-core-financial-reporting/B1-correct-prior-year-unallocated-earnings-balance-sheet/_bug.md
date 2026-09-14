---
id: B1
type: Bug
summary: "Correct prior-year unallocated earnings in Balance Sheet"
epic: E4
parent: ~
status: "To Do"
priority: Highest
story_points: 2
component: "Accounting"
labels: [accounting, balancesheet, fiscal-year]
depends_on: []
assignee: ~
due_date: 2027-04-26
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# B1 · Correct prior-year unallocated earnings in Balance Sheet

**Bug** · Highest · `To Do` · 2 pts · Accounting · due 2027-04-26 · FY2084-golive

Ensure the Balance Sheet includes prior-year earnings so it remains balanced after the first fiscal year.

## Acceptance criteria

A prior fiscal-year posting results in a balanced Balance Sheet; regression test fails if the line is removed.

## Children

- [`ST14`](./ST14-create-multi-fiscal-year-accounting-fixture.md) · Sub-task · `To Do` · Create multi-fiscal-year accounting fixture
- [`ST15`](./ST15-implement-earnings-calculation-report-assertion.md) · Sub-task · `To Do` · Implement earnings calculation and report assertion

## External prerequisites

- Representative prior-year fixture

## Source reference

- `docs/project-review/JIRA_BACKLOG.md BUG-11`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
