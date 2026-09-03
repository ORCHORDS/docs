# Retrieved Context Trust Labels

## Purpose

Control profile for **OWASP ASI06: Memory and Context Poisoning**.

## Control

Attach source trust, freshness, sensitivity, and validation state to retrieved context and preserve those labels through ranking and assembly.

## Validation

Mix stale, unverified, trusted, and sensitive records; verify the orchestrator can enforce different handling after retrieval.

## Failure correction

Correct label generation or propagation, invalidate affected context packages, and rerun downstream decisions.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
