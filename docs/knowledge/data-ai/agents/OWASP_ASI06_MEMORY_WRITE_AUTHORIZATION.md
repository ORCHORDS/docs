# Memory Write Authorization

## Purpose

Control profile for **OWASP ASI06: Memory and Context Poisoning**.

## Control

Authorize durable memory writes separately from ordinary response generation so any model output cannot silently become trusted long-term state.

## Validation

Attempt writes from user text, tool output, peer agents, and low-trust retrieval; verify policy controls which sources may persist.

## Failure correction

Disable the unsafe writer, remove unauthorized entries, and tighten write permissions by source and memory class.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
