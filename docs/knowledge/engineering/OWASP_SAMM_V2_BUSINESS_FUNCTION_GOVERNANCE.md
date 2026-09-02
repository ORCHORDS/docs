# OWASP SAMM v2 Business Function Governance

## Purpose

OWASP SAMM (Software Assurance Maturity Model) v2 organizes software security activities into five Business Functions: Governance, Design, Implementation, Verification, and Operations. Each business function is divided into practices, and each practice is broken down into maturity levels with activities and expected artifacts. This article governs the application of the SAMM v2 business function model so an engineering team can assess its current maturity, set realistic targets, and measure improvement over time.

## Scope

The model applies to any organization developing or operating software. Within this knowledge base, the article covers the SAMM v2 business functions, the maturity assessment process, the design of a maturity improvement roadmap, and the measurement of improvement over time. It does not cover specific practices in depth; readers should consult the SAMM v2 model document for each practice.

## Workflow

1. Adopt the SAMM v2 model as the assessment framework for software security. The five Business Functions (Governance, Design, Implementation, Verification, Operations) form the top-level structure.
2. Conduct an initial maturity assessment for each practice under each business function. Use the SAMM v2 maturity levels (Level 0 to Level 3) and the activities the model lists.
3. Identify gaps between the current maturity and the target maturity chosen by the organization. The target may vary by business function: a regulated product may target higher maturity in Verification; an early-stage product may focus on Governance and Operations.
4. Build a maturity improvement roadmap: prioritized initiatives, each with a target practice, a target level, an implementation plan, and a measure of success.
5. Execute the initiatives. Each initiative should produce the artifacts SAMM v2 lists for the target level (e.g., for Governance "Strategy & Metrics" at Level 2: documented security strategy with measurable goals and a published report cadence).
6. Re-assess maturity periodically (typically annually) and at the end of each major initiative. Track the maturity score over time to confirm improvement.

## Controls and evidence

SAMM evidence includes the assessment results (the current maturity scores per practice), the improvement roadmap, the artifacts produced for each initiative, and the re-assessment results. Each artifact should be tied to a SAMM v2 practice and level. The roadmap should show which practices are at which level and which initiatives target which practices.

## Validation

Validation should confirm the assessment uses the SAMM v2 model consistently, the roadmap is realistic against the assessment, each initiative produces the expected artifacts, the maturity score improves between assessments, and improvements are sustained (not lost when initiatives end). Internal audits of the artifacts provide assurance that the claimed maturity level is supported.

## Failure correction

Common failure modes: assessment is performed once and never repeated (corrective: schedule periodic re-assessment and use the results to refine the roadmap); the roadmap targets practices without operational implementation (corrective: each initiative should have an owner, a deliverable, and a measure); maturity scores are inflated relative to the actual artifacts (corrective: audit the artifacts to confirm the claimed level); improvement is concentrated in one business function and neglected in others (corrective: balance the roadmap across all five business functions).

## Limitations

SAMM v2 is a maturity model, not a process or technical control standard. The model does not prescribe specific security technologies or configurations; it lists the activities an organization should be performing at each maturity level. The model does not certify any product or organization; it provides a structured assessment. The assessment is qualitative and depends on the assessor's understanding of the model and the organization.

## Scope note

This article summarizes project-neutral engineering use of OWASP SAMM v2. It does not assert any specific organization's SAMM maturity level or claim any security certification.

## Canonical sources

- OWASP SAMM v2 — Software Assurance Maturity Model v2: https://owasp.org/www-project-samm/