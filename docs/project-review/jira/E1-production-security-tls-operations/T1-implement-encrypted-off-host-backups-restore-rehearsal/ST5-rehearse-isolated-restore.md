---
id: ST5
type: Sub-task
summary: "Rehearse isolated restore"
epic: E1
parent: T1
status: "To Do"
priority: Highest
story_points: 3
component: "Platform"
labels: [restore, acceptance]
depends_on: [ST4]
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# ST5 · Rehearse isolated restore

**Sub-task** · Highest · `To Do` · 3 pts · Platform · due 2027-05-31 · FY2084-golive

Restore a selected backup to an isolated environment and verify login attachments and reports.

## Acceptance criteria

Restore report includes timestamp source backup SHA/ID application health attachment check and sign-off.

## Depends on

- [`ST4`](./ST4-automate-database-filestore-backup.md) — Automate database and filestore backup

## Source reference

- `docs/operations/HOST_RUNBOOK.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
