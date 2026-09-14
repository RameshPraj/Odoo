---
id: T5
type: Task
summary: "Create upgrade rehearsal and migration policy"
epic: E6
parent: ~
status: "To Do"
priority: High
story_points: 3
component: "Engineering"
labels: [upgrade, migration, translations]
depends_on: [S13]
assignee: ~
due_date: 2027-05-31
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# T5 · Create upgrade rehearsal and migration policy

**Task** · High · `To Do` · 3 pts · Engineering · due 2027-05-31 · FY2084-golive

Define module versioning migration scaffolding and a scratch upgrade rehearsal that protects data and translations.

## Acceptance criteria

Upgrade rehearsal completes from a production-like copy; translations survive; version/migration checks are documented.

## Children

- [`ST28`](./ST28-pin-vendored-oca-provenance.md) · Sub-task · `To Do` · Pin vendored OCA provenance
- [`ST29`](./ST29-run-translation-preserving-upgrade-rehearsal.md) · Sub-task · `To Do` · Run translation-preserving upgrade rehearsal

## Depends on

- [`S13`](../S13-expand-deterministic-automated-test-coverage/_story.md) — Expand deterministic automated test coverage

## Source reference

- `docs/project-review/ODOO_REVIEW.md`
- `docs/project-review/TODO_REGISTER.md`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
