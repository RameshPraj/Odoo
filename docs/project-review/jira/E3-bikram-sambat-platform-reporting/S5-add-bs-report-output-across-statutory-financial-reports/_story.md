---
id: S5
type: Story
summary: "Add BS report output across statutory and financial reports"
epic: E3
parent: ~
status: "To Do"
priority: High
story_points: 3
component: "Nepal Localization"
labels: [bikram-sambat, reports, accounting]
depends_on: []
assignee: ~
due_date: 2027-04-26
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S5 · Add BS report output across statutory and financial reports

**Story** · High · `To Do` · 3 pts · Nepal Localization · due 2027-04-26 · FY2084-golive

Apply central company-configured AD BS or both-date formatting to approved QWeb financial VAT and TDS outputs.

## Acceptance criteria

PDF and HTML outputs honor company setting; report amounts and date domains remain Gregorian; output tests cover AD BS and both.

## Children

- [`ST12`](./ST12-implement-central-qweb-bs-formatter.md) · Sub-task · `To Do` · Implement central QWeb BS formatter
- [`ST13`](./ST13-convert-financial-vat-tds-templates.md) · Sub-task · `To Do` · Convert financial VAT and TDS templates

## External prerequisites

- CA decision on statutory language/output

## Source reference

- `docs/bs-calendar/REPORTING.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
