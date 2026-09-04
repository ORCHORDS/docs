# GraphQL Production Introspection Review

## Purpose

Verify that GraphQL schema introspection in production matches the API's intended audience and is disabled when the production API is not meant to expose its schema to external consumers.

## Source basis

OWASP ASVS 5.0.0 requirement v5.0.0-4.3.2 requires GraphQL introspection queries to be disabled in production unless the GraphQL API is intended for use by other parties.

## Inputs

- GraphQL production endpoint inventory;
- documented API audience and integration model;
- schema publication or developer-portal requirements;
- gateway, framework, and GraphQL server configuration;
- representative authenticated and unauthenticated roles.

## Procedure

1. **Classify the API audience.** Determine whether the production schema is intentionally public/partner-facing or is only for first-party/internal clients.
2. **Test unauthenticated introspection.** Submit standard schema-introspection operations and record whether schema metadata is returned.
3. **Test authenticated roles.** Repeat with representative low-privilege and privileged identities to identify role-dependent introspection behavior.
4. **Check alternate endpoints.** Review versioned, legacy, administrative, staging-like, federation, or gateway endpoints exposed through production routing.
5. **Review configuration provenance.** Confirm the observed behavior comes from deliberate production configuration rather than an accidental framework default.
6. **Review public-schema justification.** If introspection is enabled because third parties consume the API, verify that this is documented and that schema visibility does not substitute for authorization controls.
7. **Check error behavior.** Disabled introspection should reject the operation predictably without exposing unnecessary stack traces or internal implementation details.
8. **Review persisted or cached schema data.** Ensure a disabled introspection endpoint is not undermined by an unintended schema-documentation or debug endpoint exposing equivalent internal metadata.
9. **Retest after deployment changes.** Include introspection status in release or configuration checks when GraphQL server, gateway, or framework defaults change.
10. **Record exceptions.** Document any intentionally enabled introspection, audience, owner, risk rationale, and review date.

## Evidence

Record endpoint, environment, identity/role, introspection operation result, configuration source, intended API audience, application revision, and exception status.

## Completion criteria

The review is complete when production introspection behavior matches the documented API audience across all exposed GraphQL endpoints, unintended schema exposure is removed, and deliberate exposure has a clear owner and rationale.

## Sources

- OWASP ASVS 5.0.0, V4.3 GraphQL: https://github.com/OWASP/ASVS/blob/v5.0.0_release/5.0/en/0x13-V4-API-and-Web-Service.md
- OWASP Web Security Testing Guide, GraphQL Testing: https://owasp.org/www-project-web-security-testing-guide/stable/4-Web_Application_Security_Testing/12-API_Testing/01-Testing_GraphQL

## Scope note

Disabling introspection is not an authorization control. Every resolver and object access path still requires appropriate authentication, authorization, validation, and abuse protection.
