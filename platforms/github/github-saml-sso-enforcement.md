# github-saml-sso-enforcement

**Issue:** Enforcing SAML SSO for a GitHub organisation so all access goes through the IdP
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without SSO enforcement, members can access GitHub with their personal credentials even after being offboarded from the IdP.

## Pattern / Solution
1. Configure SAML in Org Settings → Authentication security → SAML single sign-on.
2. Set IdP metadata URL and test the connection.
3. After testing, enable "Require SAML SSO authentication" to enforce.

Members must re-authenticate through the IdP; non-compliant sessions are revoked.

PAT authorisation for SSO orgs:
```bash
# Users must authorise their PATs for the org via the GitHub UI:
# GitHub → Settings → Personal access tokens → Configure SSO → Authorise
```
Okta/Azure AD configuration:
- Entity ID: `https://github.com/orgs/myorg`
- ACS URL: `https://github.com/orgs/myorg/saml/consume`
- Attribute mapping: `login` → GitHub username, `email` → email

## Gotchas
- Existing PATs must be re-authorised for the SSO org or they stop working.
- Service accounts that use PATs must authorise through the IdP — create a SAML identity for them.
- SAML SSO does not encrypt git credentials on disk; it controls session access only.
- Enabling SAML without notifying users causes an immediate lockout for non-SSO sessions.

## Related
- `github-enterprise-managed-users.md`
- `github-ip-allow-list.md`
- `github-fine-grained-personal-access-tokens.md`
