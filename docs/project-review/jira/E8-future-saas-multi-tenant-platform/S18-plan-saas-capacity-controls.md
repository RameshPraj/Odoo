---
id: S18
type: Story
summary: "Plan SaaS capacity controls"
epic: E8
parent: ~
status: "Blocked"
priority: Medium
story_points: 5
component: "Platform"
labels: [future-saas, performance, postgresql]
depends_on: [S16]
assignee: ~
due_date: ~
fix_version: Deferred-SaaS
project_key: PROJECT_KEY
---

# S18 · Plan SaaS capacity controls

**Story** · Medium · `Blocked` · 5 pts · Platform · Deferred-SaaS

Introduce PgBouncer and cron scaling only after measured tenant-count thresholds and workload evidence.

## Acceptance criteria

Connection and cron capacity decisions are based on measured workload and target tenant count.

## Depends on

- [`S16`](./S16-implement-tenant-routing-cron-session-containment.md) — Implement tenant routing cron and session containment

## External prerequisites

- capacity baseline

## Source reference

- `docs/project-review/ROADMAP.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
