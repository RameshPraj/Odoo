---
id: ST4
type: Sub-task
summary: "Automate database and filestore backup"
epic: E1
parent: T1
status: "To Do"
priority: Highest
story_points: 3
component: "Platform"
labels: [backup, postgresql, filestore]
depends_on: [ST3]
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# ST4 · Automate database and filestore backup

**Sub-task** · Highest · `To Do` · 3 pts · Platform · due 2027-05-31 · FY2084-golive

Create a least-privilege scheduled backup job covering PostgreSQL and the active filestore.

## Acceptance criteria

Backup job exits non-zero on failure; artifacts are encrypted and off-host; logs are retained.

## Depends on

- [`ST3`](./ST3-define-backup-retention-access-policy.md) — Define backup retention and access policy

## Source reference

- `docs/project-review/POSTGRESQL.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
