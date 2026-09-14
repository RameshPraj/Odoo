---
id: S27
type: Story
summary: "Implement TDS return aggregation and filing"
epic: E5
parent: ~
status: "To Do"
priority: High
story_points: 5
component: "Accounting"
labels: [tds, return, correctness]
depends_on: [S26]
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S27 · Implement TDS return aggregation and filing

**Story** · High · `To Do` · 5 pts · Accounting · due 2027-02-15 · FY2084-golive

l10n_np.tds.return is a data shell with no methods, no file action and no tests. Certificates must be attached by hand.

## Acceptance criteria

Given a period, when the return is generated, then it collects the period certificates automatically, totals tie to the withholding lines, and it cannot be filed before it is computed.

## Depends on

- [`S26`](./S26-implement-tds-threshold-enforcement-category-linkage.md) — Implement TDS threshold enforcement and category linkage

## Source reference

- `custom_addons/l10n_np_tds/models/tds_certificate.py`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
