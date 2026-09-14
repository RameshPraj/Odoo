---
id: ST36
type: Sub-task
summary: "Load debtor and creditor sub-ledger detail"
epic: E11
parent: S23
status: "Blocked"
priority: High
story_points: 3
component: "Accounting"
labels: [migration, partners]
depends_on: []
assignee: ~
due_date: 2027-07-05
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# ST36 · Load debtor and creditor sub-ledger detail

**Sub-task** · High · `Blocked` · 3 pts · Accounting · due 2027-07-05 · FY2084-golive

Opening receivables and payables must carry per-partner detail, not a single control total.

## Acceptance criteria

Given the opening entry, when the partner ledger is run, then per-partner balances sum to the control account and each open item carries its original date.

## Source reference

- `docs/project-review/ACCOUNTING_NEPAL.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
