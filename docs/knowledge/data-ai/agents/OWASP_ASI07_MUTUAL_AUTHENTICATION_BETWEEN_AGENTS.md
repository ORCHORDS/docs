# Mutual Authentication Between Agents

## Purpose

Control profile for **OWASP ASI07: Insecure Inter-Agent Communication**.

## Control

Require both sides of privileged inter-agent communication to authenticate the peer rather than trusting network location or a self-declared agent name.

## Validation

Connect legitimate, anonymous, and impersonating peers and verify only trusted identities reach protected operations.

## Failure correction

Terminate untrusted channels, rotate compromised credentials if needed, and repair trust-bundle or peer-policy validation.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://a2a-protocol.org/dev/specification/
- https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/
