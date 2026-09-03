# Compromised Tool Revocation

## Purpose

Control profile for **OWASP ASI04: Agentic Supply Chain Vulnerabilities**.

## Control

Maintain a fast path to remove or deny a compromised tool, plugin, model adapter, or dependency across active agent catalogs and caches.

## Validation

Mark a test component revoked and verify new calls fail and stale catalog entries are invalidated within the defined objective.

## Failure correction

Disable the component, identify affected executions, rotate related credentials if exposed, and deploy a verified replacement.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://slsa.dev/spec/v1.2/
- https://docs.sigstore.dev/policy-controller/overview/
