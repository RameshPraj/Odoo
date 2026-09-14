---
id: S9
type: Story
summary: "Implement versioned IRD VAT return framework"
epic: E5
parent: ~
status: "Blocked"
priority: Highest
story_points: 5
component: "Accounting"
labels: [vat, ird, blocked-ca]
depends_on: [SP1]
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S9 · Implement versioned IRD VAT return framework

**Story** · Highest · `Blocked` · 5 pts · Accounting · due 2027-02-15 · FY2084-golive

Build editable versioned return forms and box-to-tax-tag mapping then validate an actual filing period to the rupee.

## Acceptance criteria

Filed return preserves its form version; each box traces to tagged journal lines; CA agrees results to the rupee.

## Children

- [`ST22`](./ST22-model-versioned-vat-forms-boxes.md) · Sub-task · `Blocked` · Model versioned VAT forms and boxes
- [`ST23`](./ST23-validate-vat-migration-non-zero-boxes.md) · Sub-task · `Blocked` · Validate VAT migration and non-zero boxes

## Depends on

- [`SP1`](../SP1-run-nepal-ca-statutory-configuration-workshop/_spike.md) — Run Nepal CA statutory configuration workshop

## External prerequisites

- CA-approved IRD layout

## Source reference

- `NEPAL-ACCOUNTING-BUILD-PLAN.md Phase B2`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
