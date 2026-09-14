---
id: ST23
type: Sub-task
summary: "Validate VAT migration and non-zero boxes"
epic: E5
parent: S9
status: "Blocked"
priority: Highest
story_points: 3
component: "Accounting"
labels: [vat, migration, testing]
depends_on: [ST22]
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# ST23 · Validate VAT migration and non-zero boxes

**Sub-task** · Highest · `Blocked` · 3 pts · Accounting · due 2027-02-15 · FY2084-golive

Create fixture and migration checks ensuring tagged posted invoices populate expected return boxes without skips.

## Acceptance criteria

Reverting the tag migration fails the test; domestic and export cases reconcile to the ledger.

## Depends on

- [`ST22`](./ST22-model-versioned-vat-forms-boxes.md) — Model versioned VAT forms and boxes

## Source reference

- `docs/project-review/JIRA_BACKLOG.md BUG-7 BUG-8`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
