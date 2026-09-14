---
id: B4
type: Bug
summary: "Balance Sheet header prints the fiscal year in Gregorian"
epic: E3
parent: ~
status: "To Do"
priority: Medium
story_points: 2
component: "Nepal Localization"
labels: [bikram-sambat, reporting, qweb]
depends_on: []
assignee: ~
due_date: 2027-04-26
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# B4 · Balance Sheet header prints the fiscal year in Gregorian

**Bug** · Medium · `To Do` · 2 pts · Nepal Localization · due 2027-04-26 · FY2084-golive

The financial statements template uses t-esc on raw dates for the fiscal-year line, bypassing the BS converter, so one header line shows Gregorian beside BS.

## Acceptance criteria

Given a company set to BS output, when the Balance Sheet renders, then the fiscal-year header line shows BS dates like every other date on the report.

## Source reference

- `custom_addons/account_financial_statements/report/financial_statements_templates.xml`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
