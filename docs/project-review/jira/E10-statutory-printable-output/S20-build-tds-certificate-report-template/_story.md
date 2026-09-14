---
id: S20
type: Story
summary: "Build TDS certificate report template"
epic: E10
parent: ~
status: "Blocked"
priority: Highest
story_points: 5
component: "Accounting"
labels: [tds, reporting, blocked-ca]
depends_on: [SP1]
assignee: ~
due_date: 2027-02-15
fix_version: FY2084-golive
project_key: PROJECT_KEY
---

# S20 · Build TDS certificate report template

**Story** · Highest · `Blocked` · 5 pts · Accounting · due 2027-02-15 · FY2084-golive

l10n_np_tds has no report directory, no QWeb template and no report action. A certificate must be issuable to the deductee.

## Acceptance criteria

Given an issued certificate, when it is printed, then the PDF carries every mandatory field in the CA-approved layout and the figures tie to the withholding lines.

## Children

- [`ST32`](./ST32-implement-tds-certificate-qweb-template-pdf-action.md) · Sub-task · `Blocked` · Implement TDS certificate QWeb template and PDF action
- [`ST33`](./ST33-obtain-ca-approval-tds-certificate-layout.md) · Sub-task · `Blocked` · Obtain CA approval of TDS certificate layout

## Depends on

- [`SP1`](../../E5-nepal-statutory-vat-tds-compliance/SP1-run-nepal-ca-statutory-configuration-workshop/_spike.md) — Run Nepal CA statutory configuration workshop

## External prerequisites

- CA-approved certificate layout

## Source reference

- `NEPAL-ACCOUNTING-BUILD-PLAN.md section 7 item 3`

---

_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira import artifact; edit it, then regenerate._
