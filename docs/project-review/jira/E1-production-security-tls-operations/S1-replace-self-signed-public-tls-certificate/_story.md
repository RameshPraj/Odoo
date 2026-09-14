---
id: S1
type: Story
summary: "Replace self-signed public TLS certificate"
epic: E1
parent: ~
status: "To Do"
priority: Highest
story_points: 3
component: "Platform"
labels: [production, tls, security]
depends_on: []
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S1 · Replace self-signed public TLS certificate

**Story** · Highest · `To Do` · 3 pts · Platform · due 2027-05-31 · FY2084-golive

Issue a trusted certificate for the production hostname and make all public browser and API traffic validate normally.

## Acceptance criteria

A browser validates the complete certificate chain; HTTP redirects to HTTPS; TLS renewal is automated and documented.

## Children

- [`ST1`](./ST1-confirm-production-dns-hostname.md) · Sub-task · `To Do` · Confirm production DNS hostname
- [`ST2`](./ST2-configure-acme-renewal-nginx-tls.md) · Sub-task · `To Do` · Configure ACME renewal and nginx TLS

## External prerequisites

- DNS control and approved hostname

## Source reference

- `deploy/README.md`
- `production endpoint`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
