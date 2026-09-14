---
id: S15
type: Story
summary: "Write cross-tenant isolation suite before SaaS changes"
epic: E8
parent: ~
status: "Blocked"
priority: Medium
story_points: 5
component: "Platform"
labels: [future-saas, security, testing]
depends_on: []
assignee: ~
due_date: ~
fix_version: Deferred-SaaS
project_key: PROJECT_KEY
---

# S15 · Write cross-tenant isolation suite before SaaS changes

**Story** · Medium · `Blocked` · 5 pts · Platform · Deferred-SaaS

Create two-real-database tests for routing session records cron mail and administrative boundary isolation.

## Acceptance criteria

All isolation tests pass before db_name removal or second tenant provisioning.

## Children

- [`ST30`](./ST30-test-hostile-database-selection-paths.md) · Sub-task · `Blocked` · Test hostile database selection paths
- [`ST31`](./ST31-test-session-cron-mail-containment.md) · Sub-task · `Blocked` · Test session cron and mail containment

## External prerequisites

- Approved SaaS architecture

## Source reference

- `docs/project-review/JIRA_BACKLOG.md STORY-5`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
