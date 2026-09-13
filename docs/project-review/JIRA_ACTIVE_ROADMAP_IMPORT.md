# Active Jira roadmap import

This is the current, actionable Jira backlog for the single-tenant Nepal Odoo
deployment. It replaces neither the evidence nor the historical findings in
`JIRA_BACKLOG.md`; those documents retain completed and superseded audit work.

## Import

Import `JIRA_ACTIVE_ROADMAP.csv` with Jira's CSV importer.

1. Replace every `PROJECT_KEY` value with the target project key, or map the
   column to the target project during import.
2. Map `Issue ID` to Jira's external issue identifier and map `Parent ID` to
   the parent identifier. If the target is company-managed, map `Epic ID` to
   the Epic Link field for Story, Task, Bug, and Spike rows.
3. Map the remaining columns with matching names. Keep the source-reference
   column in the description or a dedicated custom field.
4. Run a test import into a disposable project first. Verify all subtasks have
   the intended parent and every non-epic row has the intended epic.

## Conventions

- `To Do` means implementable now. `Blocked` means waiting for a named
  accountant/CA input or an explicit business decision.
- The target is the current native Ubuntu production service. Podman is only
  the localhost staging environment.
- Production promotion stays manual. Pull-request checks, merging, branch
  cleanup, immutable-image publishing, and staging deployment are automated.
- Bikram Sambat is a user-facing representation. PostgreSQL and integrations
  retain Gregorian dates.
- `FUTURE-SAAS` issues are deliberately not scheduled for the single-tenant
  go-live; they must not be started before their isolation test gate passes.

## Done evidence deliberately excluded from import

The following are not active work items: the GitHub repository/branch policy,
automated staging deployment, native Ubuntu production deployment, production
key authentication, database-manager hardening, current BS conversion coverage,
and the existing CI database/container gates. Their historical evidence remains
in the project-review, BS-calendar, deployment, and GitHub workflow records.
