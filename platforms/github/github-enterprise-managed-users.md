# github-enterprise-managed-users

**Issue:** Understanding and working with GitHub Enterprise Managed Users (EMU)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
EMU accounts are fully controlled by the enterprise IdP. They cannot access non-enterprise content, cannot create personal repos, and every identity is provisioned via SCIM.

## Pattern / Solution
EMU characteristics:
- Username pattern: `username_enterpriseshortcode`
- Accounts are provisioned/deprovisioned via SCIM (Okta, Azure AD, Entra ID)
- Members cannot join external orgs or contribute to personal repos
- All repos are within the enterprise

SCIM provisioning setup (Okta example):
1. Install the GitHub EMU app in Okta.
2. Configure with enterprise slug and a SCIM provisioning PAT.
3. Push users/groups from Okta; they appear as managed members.

Automation with EMU:
```bash
# List managed enterprise members
gh api /enterprises/myenterprise/members --jq '.[].login'

# Suspend a user (use SCIM deprovision instead for permanent removal)
gh api -X PUT /enterprises/myenterprise/members/user_slug/suspend
```

## Gotchas
- EMU users cannot have personal PATs that work outside the enterprise.
- Migrating from a standard org to EMU requires a full re-setup — there is no in-place upgrade.
- External contributors cannot use EMU accounts; use standard org membership with restricted roles.
- SCIM is the source of truth — do not manage membership via the GitHub UI/API directly.

## Related
- `github-saml-sso-enforcement.md`
- `github-organization-settings.md`
