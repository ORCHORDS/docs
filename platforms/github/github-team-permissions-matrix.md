# github-team-permissions-matrix

**Issue:** Structuring GitHub teams and repository permission levels correctly
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Ad-hoc per-user permission grants are unauditable and break when people leave. Team-based permissions scale and audit cleanly.

## Pattern / Solution
GitHub permission levels:

| Level | Can do |
|---|---|
| Read | Clone, pull, view issues |
| Triage | Manage issues/PRs (no code write) |
| Write | Push to non-protected branches |
| Maintain | Manage releases, merge PRs, no destructive admin |
| Admin | Full repo control including settings |

Recommended team structure:
```
org/
  eng-leads        → Maintain on all repos
  engineers        → Write on feature repos
  devops           → Admin on infra repos
  qa               → Triage on all repos
  external-vendor  → Read on specific repo
```
Automate via Terraform (github provider):
```hcl
resource "github_team_repository" "api" {
  team_id    = github_team.engineers.id
  repository = "api"
  permission = "push"
}
```

## Gotchas
- Individual user permissions override team permissions — audit for ghost grants.
- Nested teams inherit parent team permissions.
- `Maintain` is often the right level for senior devs; `Admin` should be rare.
- Service accounts should be org members on their own team with minimum required access.

## Related
- `github-organization-settings.md`
- `github-audit-log-api.md`
