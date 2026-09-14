---
id: ST7
type: Sub-task
summary: "Add certificate backup and disk alerts"
epic: E1
parent: S2
status: "To Do"
priority: High
story_points: 2
component: "Platform"
labels: [monitoring, tls, backup]
depends_on: [S1, T1]
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# ST7 · Add certificate backup and disk alerts

**Sub-task** · High · `To Do` · 2 pts · Platform · due 2027-05-31 · FY2084-golive

Alert before certificate expiry on failed backup and on capacity exhaustion.

## Acceptance criteria

Alert tests are recorded and routed to the named operator.

## Depends on

- [`S1`](../S1-replace-self-signed-public-tls-certificate/_story.md) — Replace self-signed public TLS certificate
- [`T1`](../T1-implement-encrypted-off-host-backups-restore-rehearsal/_task.md) — Implement encrypted off-host backups and restore rehearsal

## Source reference

- `docs/operations/HOST_RUNBOOK.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
