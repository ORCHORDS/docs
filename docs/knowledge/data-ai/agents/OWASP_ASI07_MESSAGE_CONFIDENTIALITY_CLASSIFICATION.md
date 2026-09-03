# Inter-Agent Message Confidentiality Classification

## Purpose

Control profile for **OWASP ASI07: Insecure Inter-Agent Communication**.

## Control

Classify data before sending it to another agent and enforce whether that peer and transport are approved for the sensitivity level.

## Validation

Attempt to send public, internal, and restricted test data to peers with different trust levels; verify policy gates transfer before transmission.

## Failure correction

Stop the transfer, revoke cached payloads where possible, correct classification or peer policy, and investigate disclosure.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://a2a-protocol.org/dev/specification/
- https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/
