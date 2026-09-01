# OWASP Top 10:2025 Version Governance

## Purpose

The OWASP Top 10 is an application-security awareness document that summarizes major classes of web-application risk. The current released edition is **OWASP Top 10:2025**. OWASP marks the 2021 edition as superseded and older editions as historical.

The Top 10 is useful for awareness, prioritization, training, and broad risk communication, but it should not be treated as a detailed verification standard. OWASP ASVS is better suited to concrete application-security verification requirements.

## Current 2025 categories

The released 2025 list is:

1. A01:2025 — Broken Access Control
2. A02:2025 — Security Misconfiguration
3. A03:2025 — Software Supply Chain Failures
4. A04:2025 — Cryptographic Failures
5. A05:2025 — Injection
6. A06:2025 — Insecure Design
7. A07:2025 — Authentication Failures
8. A08:2025 — Software or Data Integrity Failures
9. A09:2025 — Security Logging and Alerting Failures
10. A10:2025 — Mishandling of Exceptional Conditions

## Governance pattern

1. Record the Top 10 edition when using a category in policy, training, risk registers, or reporting.
2. Use identifiers such as `A03:2025` rather than an unversioned label such as only “Software Supply Chain Failures.”
3. Preserve mappings to prior editions when historical findings or metrics still use 2021 identifiers.
4. Do not assume category numbers remain stable across editions.
5. Use the Top 10 for broad risk framing and pair it with detailed engineering or verification standards where specific controls are needed.
6. Review dashboards, training, templates, and issue labels when adopting a new Top 10 edition so stale category names do not silently persist.
7. Avoid presenting Top 10 coverage as evidence that an application has been comprehensively security-tested.

## Relationship to ASVS

The Top 10 is explicitly an awareness document. It identifies broad categories but does not provide the same detailed, testable requirement structure as ASVS.

A practical mapping can use Top 10 categories for communication and ASVS requirement identifiers for verification evidence. The two artifacts should remain separately versioned because their release cycles and structures differ.

## Migration considerations

When moving from the 2021 edition to 2025:

- identify renamed, merged, newly emphasized, or reordered categories;
- avoid mechanically translating category numbers without reviewing meaning;
- retain the original edition on historical findings; and
- update training and metrics only after confirming the new mapping.

## Failure modes

- Referring to “A03” without an edition can point to different risk categories over time.
- Treating 2021 as current conflicts with OWASP's released 2025 edition.
- Using the Top 10 as a detailed acceptance checklist can leave important verification gaps.
- Renumbering historical findings in place can destroy auditability of earlier reports.
- Claiming “OWASP Top 10 compliant” overstates what the awareness document represents.

## Sources

- OWASP Top 10 official repository: https://github.com/OWASP/Top10
- OWASP Top 10:2025 released content: https://github.com/OWASP/Top10/blob/master/2025/docs/en/index.md
- OWASP ASVS project: https://owasp.org/www-project-application-security-verification-standard/

## Scope note

This article describes version and usage governance for the OWASP Top 10. It does not reproduce the full Top 10 content or claim that any application is secure, compliant, or verified against OWASP guidance.