---
id: ST32
type: Sub-task
summary: "Implement TDS certificate QWeb template and PDF action"
epic: E10
parent: S20
status: "Blocked"
priority: Highest
story_points: 3
component: "Accounting"
labels: [tds, qweb]
depends_on: []
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# ST32 · Implement TDS certificate QWeb template and PDF action

**Sub-task** · Highest · `Blocked` · 3 pts · Accounting · due 2027-02-15 · FY2084-golive

Add a report directory, QWeb template and ir.actions.report to l10n_np_tds.

## Acceptance criteria

Given a certificate in issued state, when the print action runs, then HTML and PDF render without error and BS dates honour the company setting.

## Source reference

- `custom_addons/l10n_np_tds`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
