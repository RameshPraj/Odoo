---
id: ST8
type: Sub-task
summary: "Verify workflow fix merged and branch deleted"
epic: E2
parent: S3
status: "To Do"
priority: High
story_points: 1
component: "Platform"
labels: [github, governance]
depends_on: []
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# ST8 · Verify workflow fix merged and branch deleted

**Sub-task** · High · `To Do` · 1 pts · Platform · due 2027-05-31 · FY2084-golive

Confirm the protected PR auto-merges after CI and its remote branch is removed by repository policy.

## Acceptance criteria

Main contains the correction; PR is merged; feature branch is deleted; required checks remain enforced.

## Source reference

- `.github/workflows/production-deploy.yml`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
