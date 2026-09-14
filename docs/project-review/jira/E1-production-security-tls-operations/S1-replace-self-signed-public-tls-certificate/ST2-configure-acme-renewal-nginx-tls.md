---
id: ST2
type: Sub-task
summary: "Configure ACME renewal and nginx TLS"
epic: E1
parent: S1
status: "To Do"
priority: Highest
story_points: 3
component: "Platform"
labels: [tls, nginx, acme]
depends_on: [ST1]
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# ST2 · Configure ACME renewal and nginx TLS

**Sub-task** · Highest · `To Do` · 3 pts · Platform · due 2027-05-31 · FY2084-golive

Install a trusted ACME certificate configure nginx and verify renewal without service interruption.

## Acceptance criteria

Strict TLS verification succeeds; renewal dry-run succeeds; no private key is in Git.

## Depends on

- [`ST1`](./ST1-confirm-production-dns-hostname.md) — Confirm production DNS hostname

## Source reference

- `deploy/README.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
