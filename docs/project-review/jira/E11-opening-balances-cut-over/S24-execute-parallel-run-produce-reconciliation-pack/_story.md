---
id: S24
type: Story
summary: "Execute parallel run and produce reconciliation pack"
epic: E11
parent: ~
status: "Blocked"
priority: Highest
story_points: 8
component: "Accounting"
labels: [migration, assurance, parallel-run]
depends_on: [S23, S21, S20]
assignee: ~
due_date: 2027-07-05
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S24 · Execute parallel run and produce reconciliation pack

**Story** · Highest · `Blocked` · 8 pts · Accounting · due 2027-07-05 · FY2084-golive

Run at least one full VAT period in both systems and reconcile to the rupee before relying on Odoo alone.

## Acceptance criteria

Given one full VAT period run in both systems, when the results are compared, then VAT return boxes, TDS deductions and the trial balance agree to the rupee, and differences are explained in writing.

## Children

- [`ST38`](./ST38-run-one-full-vat-period-parallel.md) · Sub-task · `Blocked` · Run one full VAT period in parallel
- [`ST39`](./ST39-produce-auditor-reconciliation-pack.md) · Sub-task · `Blocked` · Produce auditor reconciliation pack

## Depends on

- [`S23`](../S23-post-opening-balance-journal-at-ashad-end-2083-84/_story.md) — Post opening balance journal at Ashad end 2083/84
- [`S21`](../../E10-statutory-printable-output/S21-build-vat-return-report-template/_story.md) — Build VAT return report template
- [`S20`](../../E10-statutory-printable-output/S20-build-tds-certificate-report-template/_story.md) — Build TDS certificate report template

## Source reference

- `docs/project-review/ACCOUNTING_NEPAL.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
