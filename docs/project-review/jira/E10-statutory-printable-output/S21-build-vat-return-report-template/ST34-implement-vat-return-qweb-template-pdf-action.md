---
id: ST34
type: Sub-task
summary: "Implement VAT return QWeb template and PDF action"
epic: E10
parent: S21
status: "Blocked"
priority: Highest
story_points: 3
component: "Accounting"
labels: [vat, qweb]
depends_on: []
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# ST34 · Implement VAT return QWeb template and PDF action

**Sub-task** · Highest · `Blocked` · 3 pts · Accounting · due 2027-02-15 · FY2084-golive

Add a report directory, QWeb template and ir.actions.report to l10n_np_vat_return.

## Acceptance criteria

Given a computed return, when the print action runs, then HTML and PDF render with bilingual box labels drawn from the form definition.

## Source reference

- `custom_addons/l10n_np_vat_return`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
