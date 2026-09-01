---
title: "OWASP ASVS 5.0.0 Level Selection"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OWASP ASVS 5.0.0 Level Selection

## Pinned source and scope
ASVS **5.0.0**, released May 2025. This article uses the named version and identifiers; do not combine evidence from another edition without a migration record.

## Control interpretation
Use the ASVS 5.0 requirement identifiers. Level 1 is the minimum for all applications and emphasizes essential controls; Level 2 is the recommended target for applications handling sensitive data; Level 3 is for high-value, high-assurance, or safety-critical applications. Select a level from threat model, data classification, transaction impact, exposure, and attacker capability—not scanner coverage.

## Domain-specific procedure
Build a matrix of every V5.0 chapter and requirement ID. Mark Applicable, Not Applicable with architectural reason, or inherited with named provider evidence. Level claims require every requirement at that level and below, not an average. Sample authentication, access control, validation, cryptography, communication, configuration, data protection, logging, and business logic in deployed form.

## Evidence and decision
Preserve the completed V5.0 requirement matrix, application threat model, level rationale, and evidence link for each applicable row. Reject a level claim if any required row is untested or inherited without provider evidence.

## Failure modes
Averages, partial chapter coverage, and mixing ASVS 4.0 identifiers into a 5.0 claim invalidate the assessment.

## Sources
- [Pinned canonical source](https://github.com/OWASP/ASVS/tree/v5.0.0_release)
