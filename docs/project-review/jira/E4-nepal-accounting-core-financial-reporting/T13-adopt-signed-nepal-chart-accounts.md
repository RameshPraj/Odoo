---
id: T13
type: Task
summary: "Adopt the signed Nepal chart of accounts"
epic: E4
parent: ~
status: "Blocked"
priority: Highest
story_points: 3
component: "Accounting"
labels: [chart, nepal, blocked-ca]
depends_on: [T11, ST20]
assignee: ~
due_date: 2027-04-26
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# T13 · Adopt the signed Nepal chart of accounts

**Task** · Highest · `Blocked` · 3 pts · Accounting · due 2027-04-26 · FY2084-golive

Chart templates apply at adoption, not on upgrade, so the chart must not be adopted until the CA has signed it. Adopting the current 43-account skeleton first would force a migration to reach the signed chart - exactly what the zero-journal-entry window exists to avoid.

## Acceptance criteria

Given the CA-signed chart and zero journal entries, when the chart is adopted, then the signed accounts are active and tax tags are present on the tax repartition lines.

## Depends on

- [`T11`](./T11-set-company-country-nepal-currency-npr.md) — Set company country to Nepal and currency to NPR
- [`ST20`](../E5-nepal-statutory-vat-tds-compliance/SP1-run-nepal-ca-statutory-configuration-workshop/ST20-confirm-entity-chart-fiscal-year-policy.md) — Confirm entity chart and fiscal-year policy

## Source reference

- `docs/project-review/ACCOUNTING_NEPAL.md FIN-1`
- `NEPAL-ACCOUNTING-BUILD-PLAN.md section 7 item 1`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
