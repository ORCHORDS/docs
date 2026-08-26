# GitHub push protection delegated bypass review

**Issue:** Allowing contributors to self-bypass secret push protection turns a preventive control into a warning; broad exemptions for automation can silently reintroduce leaked credentials.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Enable delegated bypass for organization-owned repositories with the required GitHub plan and Secret Protection. Keep the reviewer set small and independent. Reserve full exemptions for tightly controlled automation that cannot use the normal request path.

GitHub documents that bypass requests expire after seven days.

## Controls

- Define reviewers through a dedicated team or custom role with only the required permission.
- Require the requester to identify whether the finding is a false positive, test-only value, or real secret and explain why removal is not feasible.
- Deny real active secrets: rotate/revoke first, remove them from the branch and history where necessary, then push clean content.
- Time-bound reviewer membership and review audit logs.
- For automation exemptions, use isolated identities, minimal repository access, short-lived credentials, and periodic necessity review.
- Escalate recurring bypasses into detector tuning or source-generation fixes.
- Prohibit approval by the requester for high-risk repositories.

## Verification

1. Test blocked pushes with safe synthetic detector fixtures.
2. Confirm ordinary contributors must request review.
3. Confirm requests expire and that approvals/denials appear in the audit trail.
4. Test exempt automation separately and alert on unexpected paths or repositories.
5. Sample approved requests and verify the recorded reason matches committed content.

## Gotchas

An exemption skips protection for all commits from the actor and can leak secrets. Organization- or enterprise-level delegated bypass can disable repository-level configuration. Push protection detects supported patterns, not every sensitive value.

## Sources

- [GitHub Docs: Bypass requests for push protection](https://docs.github.com/en/code-security/concepts/secret-security/bypass-requests)
- [GitHub Docs: Delegated bypass](https://docs.github.com/en/enterprise-cloud@latest/code-security/concepts/secret-security/about-delegated-bypass-for-push-protection)
- [GitHub Docs: Exempting trusted actors](https://docs.github.com/en/code-security/how-tos/secure-your-secrets/manage-bypass-requests/grant-exemptions)
