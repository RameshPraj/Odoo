---
id: S22
type: Story
summary: "Map spreadsheet trial balance to the signed chart"
epic: E11
parent: ~
status: "Blocked"
priority: Highest
story_points: 5
component: "Accounting"
labels: [migration, chart, blocked-ca]
depends_on: [ST20]
assignee: ~
due_date: 2027-07-05
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S22 · Map spreadsheet trial balance to the signed chart

**Story** · Highest · `Blocked` · 5 pts · Accounting · due 2027-07-05 · FY2084-golive

Produce a line-by-line mapping from the existing manual books to the CA-signed chart of accounts.

## Acceptance criteria

Given the closing trial balance, when it is mapped, then every source balance lands on exactly one target account and the mapping totals agree to the source.

## Depends on

- [`ST20`](../E5-nepal-statutory-vat-tds-compliance/SP1-run-nepal-ca-statutory-configuration-workshop/ST20-confirm-entity-chart-fiscal-year-policy.md) — Confirm entity chart and fiscal-year policy

## External prerequisites

- signed chart of accounts

## Source reference

- `NEPAL-ACCOUNTING-BUILD-PLAN.md section 7 item 1`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
