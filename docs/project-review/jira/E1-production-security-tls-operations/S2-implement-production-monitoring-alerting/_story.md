---
id: S2
type: Story
summary: "Implement production monitoring and alerting"
epic: E1
parent: ~
status: "To Do"
priority: High
story_points: 3
component: "Platform"
labels: [production, monitoring]
depends_on: []
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S2 · Implement production monitoring and alerting

**Story** · High · `To Do` · 3 pts · Platform · due 2027-05-31 · FY2084-golive

Monitor the actual silent failures relevant to Odoo rather than only host reachability.

## Acceptance criteria

Alerts cover private health PostgreSQL availability disk/backup failure Odoo crash loops and certificate expiry.

## Children

- [`ST6`](./ST6-add-health-service-probes.md) · Sub-task · `To Do` · Add health and service probes
- [`ST7`](./ST7-add-certificate-backup-disk-alerts.md) · Sub-task · `To Do` · Add certificate backup and disk alerts

## External prerequisites

- Monitoring destination and on-call owner

## Source reference

- `docs/project-review/PRODUCTION_READINESS.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
