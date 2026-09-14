---
id: T1
type: Task
summary: "Implement encrypted off-host backups and restore rehearsal"
epic: E1
parent: ~
status: "To Do"
priority: Highest
story_points: 5
component: "Platform"
labels: [production, backup, disaster-recovery]
depends_on: []
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# T1 · Implement encrypted off-host backups and restore rehearsal

**Task** · Highest · `To Do` · 5 pts · Platform · due 2027-05-31 · FY2084-golive

Automate PostgreSQL plus filestore backup to approved off-host storage and prove restoration on an isolated target.

## Acceptance criteria

Scheduled backups are encrypted; a restore produces a working isolated Odoo copy; measured RPO and RTO are recorded.

## Children

- [`ST3`](./ST3-define-backup-retention-access-policy.md) · Sub-task · `To Do` · Define backup retention and access policy
- [`ST4`](./ST4-automate-database-filestore-backup.md) · Sub-task · `To Do` · Automate database and filestore backup
- [`ST5`](./ST5-rehearse-isolated-restore.md) · Sub-task · `To Do` · Rehearse isolated restore

## External prerequisites

- Approved backup storage and retention policy

## Source reference

- `docs/project-review/POSTGRESQL.md`
- `docs/operations/HOST_RUNBOOK.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
