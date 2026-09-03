# Artifact Integrity Verification

## Purpose

Control profile for **OWASP ASI04: Agentic Supply Chain Vulnerabilities**.

## Control

Verify downloaded agent components against an expected digest, signature, or attestation immediately before installation or execution.

## Validation

Corrupt the artifact after download and verify the final execution path performs or relies on a valid integrity check.

## Failure correction

Stop deployment, fetch from a trusted source, and move verification closer to the consumption boundary.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://slsa.dev/spec/v1.2/
- https://docs.sigstore.dev/policy-controller/overview/
