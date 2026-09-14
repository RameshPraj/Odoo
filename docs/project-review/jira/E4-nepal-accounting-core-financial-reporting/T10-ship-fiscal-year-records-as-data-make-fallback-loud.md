---
id: T10
type: Task
summary: "Ship fiscal-year records as data and make the fallback loud"
epic: E4
parent: ~
status: "To Do"
priority: Highest
story_points: 5
component: "Nepal Localization"
labels: [fiscal-year, correctness, bikram-sambat]
depends_on: []
assignee: ~
due_date: 2027-04-26
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# T10 · Ship fiscal-year records as data and make the fallback loud

**Task** · Highest · `To Do` · 5 pts · Nepal Localization · due 2027-04-26 · FY2084-golive

l10n_np_fiscal_year ships no data file. Absent a record, compute_fiscalyear_dates silently falls back to a fixed day and month pair and can return a range wrong by one day.

## Acceptance criteria

Given a Nepal company and no generated fiscal year, when a statutory report is run, then the system warns or refuses rather than returning a silently wrong range; and shipped data covers BS 2075 to 2095.

## Source reference

- `custom_addons/l10n_np_fiscal_year`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
