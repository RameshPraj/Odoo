---
id: T2
type: Task
summary: "Complete production access and secret review"
epic: E1
parent: ~
status: "To Do"
priority: High
story_points: 3
component: "Platform"
labels: [security, secrets, access]
depends_on: []
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# T2 · Complete production access and secret review

**Task** · High · `To Do` · 3 pts · Platform · due 2027-05-31 · FY2084-golive

Inventory GitHub environment secrets server accounts SSH keys and sudo permissions; rotate or revoke anything no longer required.

## Acceptance criteria

No unused deploy key or credential remains; production secrets are environment-scoped; access review is signed off.

## Source reference

- `docs/project-review/SECURITY.md`
- `.github/workflows`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
