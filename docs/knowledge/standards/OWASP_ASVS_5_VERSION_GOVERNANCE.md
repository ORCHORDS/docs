# OWASP ASVS 5 Version Governance

## Purpose

The OWASP Application Security Verification Standard (ASVS) provides a structured set of application-security requirements that can be used for architecture, development, testing, procurement, and verification. The latest stable ASVS release is **5.0.0**, released in May 2025.

The ASVS repository's default development branch can contain changes intended for later patch releases, so references should pin the stable version rather than treating the moving branch as a frozen standard.

## Requirement identifiers

ASVS requirements use chapter, section, and requirement numbers such as `1.2.5`. OWASP recommends including the ASVS version in external references because requirement identifiers can move or change between releases.

A durable reference therefore uses the form:

`v<version>-<chapter>.<section>.<requirement>`

For example, `v5.0.0-1.2.5` identifies a requirement specifically within ASVS 5.0.0.

## Governance pattern

1. Record the exact stable ASVS release used by a policy, test plan, control mapping, or report.
2. Include the version in requirement identifiers stored in tickets, test results, evidence, and compliance mappings.
3. Do not automatically reinterpret an old unversioned requirement ID against a newer ASVS release.
4. When upgrading ASVS versions, compare changed, added, removed, and renumbered requirements before updating mappings.
5. Keep organization-specific verification evidence separate from the ASVS text itself; referencing a requirement is not evidence that it passes.
6. Pin automation and machine-readable requirement files to a release tag or stable release artifact rather than the repository's bleeding-edge branch.
7. Retain the previous mapping during migration so historical findings remain understandable.

## Verification levels

ASVS assigns verification levels to requirements. Projects should select a target level using risk and application context rather than automatically declaring the highest level.

A control mapping should distinguish:

- the ASVS requirement and version;
- the target verification level;
- the test or evidence used by the organization; and
- the actual result for the application under review.

## Stable versus bleeding edge

OWASP identifies 5.0.0 as the latest stable version while the main development branch may contain work toward subsequent releases. Draft or bleeding-edge content should be labeled as such and should not silently replace a stable normative baseline.

## Failure modes

- Using an unversioned requirement such as `1.2.5` can become ambiguous after a release changes numbering or content.
- Mapping to the repository's moving default branch makes historical verification difficult to reproduce.
- Treating an ASVS requirement reference as proof of implementation creates false assurance.
- Copying a target verification level without considering application risk can produce inappropriate testing scope.
- Updating requirement IDs without preserving old evidence breaks historical auditability.

## Sources

- OWASP ASVS project repository and stable-version guidance: https://github.com/OWASP/ASVS
- OWASP ASVS 5.0.0 machine-readable requirements: https://github.com/OWASP/ASVS/blob/master/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.json

## Scope note

This article describes version and reference governance for ASVS. It does not reproduce the standard or claim that any application meets an ASVS verification level.