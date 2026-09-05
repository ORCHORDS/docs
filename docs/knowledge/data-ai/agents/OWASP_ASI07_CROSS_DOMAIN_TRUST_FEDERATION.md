# Cross-Domain Agent Trust Federation

## Purpose

Control profile for **OWASP ASI07: Insecure Inter-Agent Communication**.

## Control

Make trust between agent security domains explicit, scoped, and revocable; do not infer federation merely because cryptographic credentials are valid.

## Validation

Present identities from trusted and non-federated domains and verify only configured trust relationships are accepted.

## Failure correction

Remove unintended federation entries, refresh trust bundles, and review cross-domain sessions opened under bad configuration.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/
- https://a2a-protocol.org/dev/specification/
