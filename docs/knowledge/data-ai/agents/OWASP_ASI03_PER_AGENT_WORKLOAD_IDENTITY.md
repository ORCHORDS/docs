# Per-Agent Workload Identity

## Purpose

Control profile for **OWASP ASI03: Identity and Privilege Abuse**.

## Control

Give each deployed agent workload a distinct cryptographic identity instead of sharing a broad service credential across unrelated agents or roles.

## Validation

Attempt to use one agent's identity from another workload and verify authentication or authorization fails.

## Failure correction

Revoke shared credentials, issue workload-scoped identities, and update authorization policies to use the new principal boundaries.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/
- https://www.rfc-editor.org/rfc/rfc9700
