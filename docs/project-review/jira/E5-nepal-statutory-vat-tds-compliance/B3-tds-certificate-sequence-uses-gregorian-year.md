---
id: B3
type: Bug
summary: "TDS certificate sequence uses the Gregorian year"
epic: E5
parent: ~
status: "To Do"
priority: High
story_points: 2
component: "Accounting"
labels: [tds, sequence, bikram-sambat]
depends_on: []
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# B3 · TDS certificate sequence uses the Gregorian year

**Bug** · High · `To Do` · 2 pts · Accounting · due 2027-02-15 · FY2084-golive

The sequence prefix interpolates range_year, so certificates read TDS/2026 where the fiscal year is 2083/84, and the series rolls over mid Nepali fiscal year.

## Acceptance criteria

Given a certificate issued in Bhadra 2083, when its number is inspected, then it cites the Nepali fiscal year and the series does not roll over before Ashad end.

## Source reference

- `docs/project-review/ACCOUNTING_NEPAL.md ACC-6`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
