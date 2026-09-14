---
id: T7
type: Task
summary: "Audit attachment integrity on recovery cycles"
epic: E7
parent: ~
status: "To Do"
priority: High
story_points: 2
component: "Platform"
labels: [filestore, backup, integrity]
depends_on: [T1]
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# T7 · Audit attachment integrity on recovery cycles

**Task** · High · `To Do` · 2 pts · Platform · due 2027-05-31 · FY2084-golive

Include attachment byte-read and filestore/database consistency checks in scheduled recovery verification.

## Acceptance criteria

Recovery verification identifies referenced missing blobs and proves representative business attachment downloads.

## Depends on

- [`T1`](../E1-production-security-tls-operations/T1-implement-encrypted-off-host-backups-restore-rehearsal/_task.md) — Implement encrypted off-host backups and restore rehearsal

## Source reference

- `docs/project-review/POSTGRESQL.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
