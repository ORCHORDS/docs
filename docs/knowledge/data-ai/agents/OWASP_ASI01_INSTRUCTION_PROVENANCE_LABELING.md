# Instruction Provenance Labeling

## Purpose

Control profile for **OWASP ASI01: Agent Goal Hijack**. It is implementation guidance, not an OWASP-mandated mechanism or certification claim.

## Control

Attach provenance and trust labels to user instructions, system policy, retrieved content, tool output, and peer-agent messages so orchestration does not treat all natural-language text as equal authority.

## Validation

Feed identical instruction text from different origins and verify authority changes with provenance rather than wording.

## Failure correction

Correct the source classification or ingestion path, invalidate affected context, and replay the task with repaired provenance labels.

## Limitations

Labels are useful only if the enforcement point preserves and consumes them. ACS is public preview and must not be represented as independent certification.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
