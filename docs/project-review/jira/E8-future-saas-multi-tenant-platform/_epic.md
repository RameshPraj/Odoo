---
id: E8
type: Epic
summary: "Future SaaS multi-tenant platform"
epic: ~
parent: ~
status: "Blocked"
priority: Medium
story_points: ~
component: "Platform"
labels: [future-saas, multi-tenant]
depends_on: []
assignee: ~
due_date: ~
fix_version: Deferred-SaaS
project_key: PROJECT_KEY
---

# E8 · Future SaaS multi-tenant platform

**Epic** · Medium · `Blocked` · Platform · Deferred-SaaS

Future only: build tenant isolation provisioning lifecycle and scale controls after the single-tenant product is stable.

## Acceptance criteria

No tenant is onboarded until isolation lifecycle and recovery gates pass.

## Children

- [`S15`](./S15-write-cross-tenant-isolation-suite-before-saas-changes/_story.md) · Story · `Blocked` · Write cross-tenant isolation suite before SaaS changes
- [`S16`](./S16-implement-tenant-routing-cron-session-containment.md) · Story · `Blocked` · Implement tenant routing cron and session containment
- [`S17`](./S17-automate-tenant-provisioning-suspension-offboarding.md) · Story · `Blocked` · Automate tenant provisioning suspension offboarding and restore
- [`S18`](./S18-plan-saas-capacity-controls.md) · Story · `Blocked` · Plan SaaS capacity controls

## Source reference

- `docs/project-review/SAAS_MULTI_TENANCY.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
