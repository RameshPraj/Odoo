---
id: S3
type: Story
summary: "Complete and verify production promotion workflow"
epic: E2
parent: ~
status: "To Do"
priority: Highest
story_points: 3
component: "Platform"
labels: [ci-cd, production, github-actions]
depends_on: []
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S3 · Complete and verify production promotion workflow

**Story** · Highest · `To Do` · 3 pts · Platform · due 2027-05-31 · FY2084-golive

Merge the native production bootstrap correction and test a no-op or approved promotion through the final workflow path.

## Acceptance criteria

Workflow streams the approved deployment script before checkout; captures rollback revision; uses key-verified SSH; validates loopback health.

## Children

- [`ST8`](./ST8-verify-workflow-fix-merged-branch-deleted.md) · Sub-task · `To Do` · Verify workflow fix merged and branch deleted
- [`ST9`](./ST9-exercise-controlled-deployment-audit.md) · Sub-task · `To Do` · Exercise controlled deployment audit

## External prerequisites

- Current workflow-fix PR CI

## Source reference

- `.github/workflows/production-deploy.yml`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
