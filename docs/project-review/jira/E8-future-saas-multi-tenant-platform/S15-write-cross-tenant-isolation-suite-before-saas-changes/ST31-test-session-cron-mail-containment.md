---
id: ST31
type: Sub-task
summary: "Test session cron and mail containment"
epic: E8
parent: S15
status: "Blocked"
priority: Medium
story_points: 3
component: "Platform"
labels: [future-saas, security, cron]
depends_on: []
assignee: ~
due_date: ~
fix_version: Deferred-SaaS
project_key: PROJECT_KEY
---

# ST31 · Test session cron and mail containment

**Sub-task** · Medium · `Blocked` · 3 pts · Platform · Deferred-SaaS

Prove tenant A cannot revoke tenant B sessions and a suspended tenant runs no cron or mail.

## Acceptance criteria

Tests demonstrate zero cross-tenant session cron and mail effects.

## Source reference

- `docs/project-review/JIRA_BACKLOG.md BUG-4 BUG-5`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
