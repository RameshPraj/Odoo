---
id: ST30
type: Sub-task
summary: "Test hostile database selection paths"
epic: E8
parent: S15
status: "Blocked"
priority: Medium
story_points: 3
component: "Platform"
labels: [future-saas, security]
depends_on: []
assignee: ~
due_date: ~
fix_version: Deferred-SaaS
project_key: PROJECT_KEY
---

# ST30 · Test hostile database selection paths

**Sub-task** · Medium · `Blocked` · 3 pts · Platform · Deferred-SaaS

Test Host X-Forwarded-Host query db header and authentication database selection against non-matching tenant access.

## Acceptance criteria

Forged routing inputs cannot select another tenant database.

## Source reference

- `docs/project-review/SAAS_MULTI_TENANCY.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
