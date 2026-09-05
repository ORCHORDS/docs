---
title: "OWASP Top 10 Verification Review Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "OWASP Top 10 (current published version, 2021); https://owasp.org/Top10/"
---

# OWASP Top 10 Verification Review Reference Card

## Scope

Reference card for the OWASP Top 10, the standard awareness document for the ten most critical web-application security risks. The current published list (2021) covers: A01 Broken Access Control, A02 Cryptographic Failures, A03 Injection, A04 Insecure Design, A05 Security Misconfiguration, A06 Vulnerable and Outdated Components, A07 Identification and Authentication Failures, A08 Software and Data Integrity Failures, A09 Security Logging and Monitoring Failures, A10 Server-Side Request Forgery (SSRF). Profiles that govern web-application security should cite the OWASP Top 10 and bind to NIST SP 800-53 Rev. 5, the NIST SSDF, and SLSA.

## Identifier table

| Field | Value |
| --- | --- |
| Primary source | OWASP Top 10 (current published version) |
| Companion artifacts | NIST SP 800-53 Rev. 5, NIST SSDF SP 800-218, SLSA, OWASP ASVS |
| Source URL | https://owasp.org/Top10/ |

## Plan

1. Reference the OWASP Top 10 by current version in application-security policy and SDLC documentation.
2. Map the OWASP Top 10 to internal security controls and testing requirements.
3. Apply the OWASP Top 10 to threat modeling, secure design review, code review, and security testing.
4. Apply specific controls per category:
   - A01 Broken Access Control: deny by default, enforce record-level authorization, log access-control failures.
   - A02 Cryptographic Failures: classify data, encrypt at rest and in transit, use strong algorithms and key management.
   - A03 Injection: parameterized queries, output encoding, ORM usage, no dynamic SQL.
   - A04 Insecure Design: threat modeling, secure design patterns, defense-in-depth, reference architectures.
   - A05 Security Misconfiguration: hardened baselines, automated configuration scanning, minimal install.
   - A06 Vulnerable and Outdated Components: SBOM, dependency scanning, patch SLA.
   - A07 Identification and Authentication Failures: MFA, strong password storage (Argon2/bcrypt), session management.
   - A08 Software and Data Integrity Failures: signed releases, integrity verification, CI/CD pipeline security.
   - A09 Security Logging and Monitoring Failures: structured logs, correlation IDs, alerting on security events.
   - A10 SSRF: allow-list egress destinations, network segmentation, disable unused URL schemes.
5. Bind to NIST SSDF SP 800-218 for the SDLC treatment.
6. Bind to SLSA for the supply-chain integrity treatment.
7. Bind to NIST SP 800-53 Rev. 5 for the control catalog.
8. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- OWASP Top 10 (current version).
- Application-security policy and SDLC documentation.
- Threat model and secure design review records.
- Security testing output (SAST, DAST, IAST, penetration test).
- SBOM and dependency-scan output.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats the OWASP Top 10 as the canonical awareness document for web-application security risks. Profiles that govern web applications should cite the OWASP Top 10 by version, map the categories to internal controls, apply the categories to threat modeling and testing, and bind to NIST SSDF, SLSA, and NIST SP 800-53.

A profile that governs web-application security without binding to the OWASP Top 10 is non-conformant.

## Implementation Notes

- The OWASP Top 10 is an awareness document, not a standard; for prescriptive requirements, use the OWASP ASVS (Application Security Verification Standard).
- A01 Broken Access Control is consistently the highest-impact category in production; prioritize access-control review.
- A02 Cryptographic Failures requires binding to NIST SP 800-131A algorithm assurance and the key-management policy.
- A06 Vulnerable and Outdated Components requires a working SBOM and a defined patch SLA per severity.
- A08 Software and Data Integrity Failures requires CI/CD pipeline integrity (signed releases, signed commits, SLSA Build Level 3 or higher).

## Companion Documents

- [NIST SSDF SP 800-218](NIST_SSDF_SP_800_218.md)
- [Supply Chain Levels for Software Artifacts (SLSA)](SUPPLY_CHAIN_LEVELS_SOFTWARE_ARTIFACTS.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- [OWASP Secrets Management Cheat Sheet](OWASP_SECRETS_MANAGEMENT_CHEAT_SHEET.md)
