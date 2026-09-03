# Tool Result Taint Tracking

## Purpose

Control profile for **OWASP ASI02: Tool Misuse and Exploitation**.

## Control

Carry trust and sensitivity metadata from tool results into later decisions so untrusted or sensitive outputs cannot be freely reused as instructions or destinations.

## Validation

Trace a tainted value through summarization, memory, and a second tool call; verify the label persists to the enforcement point.

## Failure correction

Stop downstream use, correct the propagation gap, and reprocess affected results with intended labels.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
