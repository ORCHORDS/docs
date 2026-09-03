# Inter-Agent Message Schema Validation

## Purpose

Control profile for **OWASP ASI07: Insecure Inter-Agent Communication**.

## Control

Validate inter-agent message structure, required fields, types, size, and extension handling before business logic consumes the payload.

## Validation

Send missing, duplicated, oversized, unknown, and type-confused fields; verify parser failures are safe and deterministic.

## Failure correction

Reject malformed channel input, update schema validation, and add the payload to protocol conformance tests.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://a2a-protocol.org/dev/specification/
- https://genai.owasp.org/resource/agent-control-standard-acs/
