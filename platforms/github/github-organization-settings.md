# github-organization-settings

**Issue:** Key GitHub organisation settings that affect security and developer experience
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Default org settings are permissive. A new org needs a security baseline before onboarding repositories.

## Pattern / Solution
Recommended org-level settings:
```
Member privileges:
  Base permissions: Read (not Write)
  Repository creation: Disabled or Org members only
  Repository forking: Disabled for private repos

Actions:
  Allow select actions: Only actions from verified creators
  Workflow permissions: Read repository contents (no write default)

Security:
  Two-factor authentication: Required for all members
  Dependabot security updates: Enabled for all repos
  Secret scanning: Enabled for all repos
  Push protection: Enabled for all repos
```
Enforce 2FA via API:
```bash
gh api -X PATCH orgs/myorg -f two_factor_requirement_enabled=true
```

## Gotchas
- Changing base permissions from Write to Read can break existing automations that relied on write access.
- Requiring 2FA immediately locks out non-compliant members — notify in advance.
- Actions policy changes take effect immediately, potentially breaking existing workflows.
- Audit log retains 90 days for non-Enterprise plans.

## Related
- `github-team-permissions-matrix.md`
- `github-audit-log-api.md`
- `github-saml-sso-enforcement.md`
