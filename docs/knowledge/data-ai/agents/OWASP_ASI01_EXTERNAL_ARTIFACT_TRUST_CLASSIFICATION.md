# External Artifact Trust Classification

## Purpose

Control profile for **OWASP ASI01: Agent Goal Hijack**.

## Control

Classify external documents, email, web content, attachments, and generated artifacts by source trust before their contents enter planning or memory.

## Validation

Mix trusted and untrusted artifacts containing equivalent instructions; verify trust classification controls whether the text can influence privileged decisions.

## Failure correction

Downgrade misclassified sources, purge derived context where needed, and correct the ingestion rule that granted excess authority.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
