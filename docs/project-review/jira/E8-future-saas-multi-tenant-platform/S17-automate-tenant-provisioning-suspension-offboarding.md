---
id: S17
type: Story
summary: "Automate tenant provisioning suspension offboarding and restore"
epic: E8
parent: ~
status: "Blocked"
priority: Medium
story_points: 5
component: "Platform"
labels: [future-saas, lifecycle, backup]
depends_on: [S16, T1]
assignee: ~
due_date: ~
fix_version: Deferred-SaaS
project_key: PROJECT_KEY
---

# S17 · Automate tenant provisioning suspension offboarding and restore

**Story** · Medium · `Blocked` · 5 pts · Platform · Deferred-SaaS

Provide audited lifecycle scripts for tenant database filestore mail routing backup restore and secure deletion.

## Acceptance criteria

A tenant can be provisioned suspended restored and offboarded with no residue and documented evidence.

## Depends on

- [`S16`](./S16-implement-tenant-routing-cron-session-containment.md) — Implement tenant routing cron and session containment
- [`T1`](../E1-production-security-tls-operations/T1-implement-encrypted-off-host-backups-restore-rehearsal/_task.md) — Implement encrypted off-host backups and restore rehearsal

## Source reference

- `docs/project-review/SAAS_MULTI_TENANCY.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
