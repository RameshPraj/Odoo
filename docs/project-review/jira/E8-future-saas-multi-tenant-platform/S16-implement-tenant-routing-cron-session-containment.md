---
id: S16
type: Story
summary: "Implement tenant routing cron and session containment"
epic: E8
parent: ~
status: "Blocked"
priority: Medium
story_points: 5
component: "Platform"
labels: [future-saas, security, routing]
depends_on: [S15]
assignee: ~
due_date: ~
fix_version: Deferred-SaaS
project_key: PROJECT_KEY
---

# S16 · Implement tenant routing cron and session containment

**Story** · Medium · `Blocked` · 5 pts · Platform · Deferred-SaaS

Apply anchored dbfilter proxy header pinning cron allowlist and chosen session isolation design as one safe release.

## Acceptance criteria

Two tenants route only by real host; no cross-tenant cron/session behavior; all isolation tests pass.

## Depends on

- [`S15`](./S15-write-cross-tenant-isolation-suite-before-saas-changes/_story.md) — Write cross-tenant isolation suite before SaaS changes

## External prerequisites

- approved architecture

## Source reference

- `docs/project-review/SAAS_MULTI_TENANCY.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
