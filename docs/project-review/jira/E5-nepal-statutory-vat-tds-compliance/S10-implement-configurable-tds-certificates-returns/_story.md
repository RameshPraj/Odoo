---
id: S10
type: Story
summary: "Implement configurable TDS certificates and returns"
epic: E5
parent: ~
status: "Blocked"
priority: Highest
story_points: 5
component: "Accounting"
labels: [tds, blocked-ca]
depends_on: [SP1]
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S10 · Implement configurable TDS certificates and returns

**Story** · Highest · `Blocked` · 5 pts · Accounting · due 2027-02-15 · FY2084-golive

Complete effective-dated TDS configuration deduction certificate and periodic return workflows using CA-approved data.

## Acceptance criteria

Rates are editable and date-bounded; certificates and returns reproduce CA-approved sample periods.

## Children

- [`ST24`](./ST24-configure-effective-dated-tds-categories.md) · Sub-task · `Blocked` · Configure effective-dated TDS categories
- [`ST25`](./ST25-render-validate-tds-certificate-return.md) · Sub-task · `Blocked` · Render and validate TDS certificate and return

## Depends on

- [`SP1`](../SP1-run-nepal-ca-statutory-configuration-workshop/_spike.md) — Run Nepal CA statutory configuration workshop

## Source reference

- `NEPAL-ACCOUNTING-BUILD-PLAN.md Phase B1`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
