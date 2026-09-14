---
id: T9
type: Task
summary: "Effective-date the VAT standard rate"
epic: E5
parent: ~
status: "To Do"
priority: High
story_points: 3
component: "Accounting"
labels: [vat, configuration, finance-act]
depends_on: []
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# T9 · Effective-date the VAT standard rate

**Task** · High · `To Do` · 3 pts · Accounting · due 2027-02-15 · FY2084-golive

TDS rates and VAT form versions are properly date-bounded; the 13 percent rate itself is a bare CSV value with no historical-correctness mechanism.

## Acceptance criteria

Given a rate change with an effective date, when a historical period is recomputed, then it uses the rate in force on the transaction date.

## Source reference

- `custom_addons/l10n_np/data/template/account.tax-np.csv`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
