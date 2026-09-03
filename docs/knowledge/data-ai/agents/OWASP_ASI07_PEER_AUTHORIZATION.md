# Peer Agent Authorization

## Purpose

Control profile for **OWASP ASI07: Insecure Inter-Agent Communication**.

## Control

Authorize authenticated peer agents for each requested action and resource; successful peer authentication alone must not grant broad capabilities.

## Validation

Use a legitimate peer identity to request actions outside its role and verify authorization denies them.

## Failure correction

Revoke excess grants, narrow peer policies, and review prior actions made under the over-broad role.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://a2a-protocol.org/dev/specification/
- https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/
