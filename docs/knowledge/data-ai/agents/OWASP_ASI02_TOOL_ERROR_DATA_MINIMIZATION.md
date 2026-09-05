# Tool Error Data Minimization

## Purpose

Control profile for **OWASP ASI02: Tool Misuse and Exploitation**.

## Control

Return enough failure information for recovery without exposing credentials, internal secrets, private data, or sensitive service internals to model context.

## Validation

Trigger authentication, validation, and backend failures and inspect the exact error content stored in traces and prompts.

## Failure correction

Redact or remap the error at the boundary, purge leaked telemetry where feasible, and rotate any exposed secret.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://genai.owasp.org/resource/agent-control-standard-acs/
