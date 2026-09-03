# Dependency Provenance Policy

## Purpose

Control profile for **OWASP ASI04: Agentic Supply Chain Vulnerabilities**.

## Control

Evaluate provenance for critical agent dependencies against policy such as expected source, build platform, review process, and attestation identity.

## Validation

Present artifacts with valid signatures but unexpected provenance fields and verify trust is not reduced to signature validity alone.

## Failure correction

Reject the artifact, update provenance constraints if the change is legitimate, and require a new reviewed release.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://slsa.dev/spec/v1.2/
- https://docs.sigstore.dev/policy-controller/overview/
