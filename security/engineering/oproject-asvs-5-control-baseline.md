# OWASP ASVS 5 control baseline

**Issue:** Security requirements expressed only as “follow OWASP” are ambiguous, difficult to test, and prone to version drift.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Adopt OWASP Application Security Verification Standard 5.0.0 as a requirements catalog for application-security verification. Record the exact ASVS version and selected verification level per system. OWASP announced ASVS 5.0.0 on 30 May 2025.

ASVS is a verification baseline, not a certification claim. Map requirements to system-specific controls and retain evidence for each applicable item.

## Implementation

1. Define the application boundary, data classification, threat model, exposed interfaces, and trust dependencies.
2. Select a target ASVS level based on risk; document any chapter- or requirement-level tailoring.
3. Import stable ASVS requirement identifiers into the control matrix.
4. Assign each requirement an owner, implementation location, verification method, evidence link, status, and review date.
5. Prefer automated tests for repeatable properties, but use design review and manual testing where automation cannot establish the claim.
6. Mark non-applicable requirements only with a system-specific rationale and reviewer.
7. Pin the ASVS version in policy and migration work; do not mix requirement identifiers from different releases.
8. Reassess after architecture, authentication, cryptography, data-flow, or deployment-boundary changes.

## Verification

- Trace a sample from ASVS requirement to code/configuration, test, and current evidence.
- Run abuse cases in an isolated test environment.
- Ensure failures block release when the mapped risk requires it.
- Review evidence freshness and confirm tests exercised production-equivalent settings.
- Have an independent reviewer challenge exclusions and compensating controls.

## Gotchas

- Passing a generic scanner does not demonstrate ASVS coverage.
- The OWASP Top 10 is an awareness list and is not a substitute for ASVS requirements.
- Copying every requirement without applicability analysis creates checkbox noise.
- Never place secrets, production tokens, or sensitive exploit payloads in evidence.

## Sources

- [OWASP Application Security Verification Standard project](https://owasp.org/www-project-application-security-verification-standard/)
- [OWASP ASVS releases](https://github.com/OWASP/ASVS/releases)
