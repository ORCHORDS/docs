---
title: "NIST SP 800-115 Technical Guide to Information Security Testing Template Governance"
standard: "NIST SP 800-115 (Technical Guide to Information Security Testing and Assessment)"
publisher: "National Institute of Standards and Technology"
category: "governance-template"
subcategory: "security-testing-and-assessment"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/115/final"
status: "approved"
classification: "public"
audience: "security testing, red team, blue team, GRC"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# NIST SP 800-115 — Technical Guide to Information Security Testing Template Governance

## Profile

This template governs the planning, execution, and reporting of technical security testing and assessment activities. It applies NIST SP 800-115's guidance for selecting techniques — review, testing, and examination — that match the assessment objective, system risk, and available evidence.

## Identifier table

| Field | Value |
| --- | --- |
| Standard | NIST SP 800-115 |
| Title | Technical Guide to Information Security Testing and Assessment |
| Publisher | NIST Computer Security Resource Center |
| Topic | Security Testing and Assessment |
| Governance role | Technical security assessment programme governance |

## Scope

The template applies to:

- Security test planning including objectives, scope, rules of engagement, and success criteria.
- Technique selection among documentation review, log review, vulnerability scanning, penetration testing, and configuration review.
- Test execution under documented change windows and emergency exception handling.
- Findings management with severity, affected assets, and remediation ownership.
- Reporting and re-testing cycles that close findings and capture lessons learned.
- Coordination with system owners, change management, and legal counsel.

## Plan / Inputs

- Scope statement with explicit in-scope and out-of-scope systems, including test data assumptions.
- Rules of engagement covering permitted techniques, testing hours, and escalation contacts.
- Test data and credential handling policy to ensure no production impact or data exposure.
- Findings intake form, severity rubric, and remediation SLA matrix.
- Communication plan for in-flight critical findings that demand immediate attention.

## ORCHORDS Profile table

| ORCHORDS field | Guidance |
| --- | --- |
| Test ID | Stable identifier of the assessment engagement. |
| Technique | Review, test, or examination as defined in NIST SP 800-115. |
| Scope | System, environment, and data classes covered. |
| Risk rating | Combination of exploitability, impact, and exposure. |
| Evidence | Output artefact reference (screenshot, request-response, configuration diff). |
| Remediation owner | Team or individual accountable for fix. |
| Verification status | Open, in progress, fixed, accepted risk, or false positive. |

## Implementation Notes

- Tailor the technique to the objective: scanning for coverage, penetration testing for adversary simulation, review for control evidence.
- Combine external and internal perspectives; perimeter and identity attack paths often differ in severity.
- Coordinate high-impact testing (DoS simulation, destructive payload) with change management and customer success in advance.
- Establish a documented exceptions register so that accepted risks have compensating control evidence.
- Re-test on a defined cadence rather than waiting for the next annual assessment to validate remediation.

## Companion Documents

- NIST SP 800-115 (canonical)
- NIST SP 800-53A Rev 5 (Assessing Security and Privacy Controls)
- OWASP Web Security Testing Guide and Mobile Security Testing Guide
- PTES (Penetration Testing Execution Standard)
- NIST SP 800-181 (Workforce Framework for Cybersecurity)
