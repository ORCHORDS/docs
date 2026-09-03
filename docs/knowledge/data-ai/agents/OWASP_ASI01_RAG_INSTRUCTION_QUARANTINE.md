# RAG Instruction Quarantine

## Purpose

Control profile for **OWASP ASI01: Agent Goal Hijack**.

## Control

Keep retrieved knowledge in a context channel whose contents can support reasoning but cannot directly redefine system policy or the user-approved objective.

## Validation

Seed retrieval data with plausible policy text and malicious goal changes; verify retrieval affects evidence selection but not authority.

## Failure correction

Remove or quarantine poisoned records, rebuild affected indexes when necessary, and record the source and detection path for future screening.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
