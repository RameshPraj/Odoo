---
id: S26
type: Story
summary: "Implement TDS threshold enforcement and category linkage"
epic: E5
parent: ~
status: "To Do"
priority: Highest
story_points: 5
component: "Accounting"
labels: [tds, correctness]
depends_on: []
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S26 · Implement TDS threshold enforcement and category linkage

**Story** · Highest · `To Do` · 5 pts · Accounting · due 2027-02-15 · FY2084-golive

threshold is declared and documented but no code reads it, and certificate line category_id is never populated, so a certificate cannot state which rate applied.

## Acceptance criteria

Given cumulative payments below the threshold, when withholding is computed, then no TDS is deducted; and given a collected certificate line, when it is inspected, then category_id names the applicable category and legal reference.

## Source reference

- `custom_addons/l10n_np_tds/models/tds_category.py`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
