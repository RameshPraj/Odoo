---
id: S21
type: Story
summary: "Build VAT return report template"
epic: E10
parent: ~
status: "Blocked"
priority: Highest
story_points: 5
component: "Accounting"
labels: [vat, ird, reporting, blocked-ca]
depends_on: [S9]
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S21 · Build VAT return report template

**Story** · Highest · `Blocked` · 5 pts · Accounting · due 2027-02-15 · FY2084-golive

l10n_np_vat_return computes boxes but has no printable output and no filing export.

## Acceptance criteria

Given a computed return, when it is printed, then the output reproduces the IRD form box for box and every figure traces to tagged journal lines.

## Children

- [`ST34`](./ST34-implement-vat-return-qweb-template-pdf-action.md) · Sub-task · `Blocked` · Implement VAT return QWeb template and PDF action
- [`ST35`](./ST35-obtain-ca-approval-vat-return-layout.md) · Sub-task · `Blocked` · Obtain CA approval of VAT return layout

## Depends on

- [`S9`](../../E5-nepal-statutory-vat-tds-compliance/S9-implement-versioned-ird-vat-return-framework/_story.md) — Implement versioned IRD VAT return framework

## External prerequisites

- CA-approved IRD layout

## Source reference

- `NEPAL-ACCOUNTING-BUILD-PLAN.md Phase B2`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
