---
id: B2
type: Bug
summary: "Export fiscal position auto-applies to foreign vendors"
epic: E5
parent: ~
status: "To Do"
priority: Highest
story_points: 3
component: "Accounting"
labels: [vat, fiscal-position, correctness]
depends_on: []
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# B2 · Export fiscal position auto-applies to foreign vendors

**Bug** · Highest · `To Do` · 3 pts · Accounting · due 2027-02-15 · FY2084-golive

The Export position has auto_apply with no country and no country group, so it zero-rates import purchases. Nepali reverse-charge on imported services would make that wrong.

## Acceptance criteria

Given a foreign vendor bill, when the fiscal position is resolved, then the export zero-rating does not apply to purchases, proven by a regression test.

## Source reference

- `docs/project-review/ACCOUNTING_NEPAL.md ACC-4`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
