---
id: T3
type: Task
summary: "Set runner and Podman staging operational checks"
epic: E2
parent: ~
status: "To Do"
priority: High
story_points: 3
component: "Platform"
labels: [staging, podman, runner]
depends_on: [S2]
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# T3 · Set runner and Podman staging operational checks

**Task** · High · `To Do` · 3 pts · Platform · due 2027-05-31 · FY2084-golive

Detect an offline Windows staging runner stopped Podman machine failed registry login or stale staging health.

## Acceptance criteria

Runner availability Podman machine container health and staging endpoint are observable; recovery instructions are tested.

## Depends on

- [`S2`](../E1-production-security-tls-operations/S2-implement-production-monitoring-alerting/_story.md) — Implement production monitoring and alerting _(monitoring destination)_

## Source reference

- `deploy/podman/README.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
