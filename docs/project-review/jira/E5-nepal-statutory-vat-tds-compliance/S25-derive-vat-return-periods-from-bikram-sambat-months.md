---
id: S25
type: Story
summary: "Derive VAT return periods from Bikram Sambat months"
epic: E5
parent: ~
status: "To Do"
priority: Highest
story_points: 3
component: "Accounting"
labels: [vat, bikram-sambat, ird]
depends_on: []
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S25 · Derive VAT return periods from Bikram Sambat months

**Story** · Highest · `To Do` · 3 pts · Accounting · due 2027-02-15 · FY2084-golive

VAT return date_from and date_to are plain date fields with no default and no BS-month generator, yet Nepali VAT is filed per BS month.

## Acceptance criteria

Given a BS month and year, when a VAT return is created, then date_from and date_to are the correct Gregorian boundaries of that BS month, proven by test across a full year.

## Source reference

- `custom_addons/l10n_np_vat_return/models/vat_return.py`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
