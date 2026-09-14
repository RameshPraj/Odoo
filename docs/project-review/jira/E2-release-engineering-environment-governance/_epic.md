---
id: E2
type: Epic
summary: "Release engineering and environment governance"
epic: ~
parent: ~
status: "To Do"
priority: Highest
story_points: ~
component: "Platform"
labels: [ci-cd, staging, production]
depends_on: []
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# E2 · Release engineering and environment governance

**Epic** · Highest · `To Do` · Platform · due 2027-05-31 · FY2084-golive

Keep PR quality staging automation and manual production promotion reliable auditable and recoverable.

## Acceptance criteria

Every release is traceable from PR to tested staged revision to manual production promotion.

## Children

- [`S3`](./S3-complete-verify-production-promotion-workflow/_story.md) · Story · `To Do` · Complete and verify production promotion workflow
- [`T3`](./T3-set-runner-podman-staging-operational-checks.md) · Task · `To Do` · Set runner and Podman staging operational checks
- [`T4`](./T4-document-release-rollback-change-approval.md) · Task · `To Do` · Document release rollback and change approval

## Source reference

- `.github/workflows`
- `deploy/`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
