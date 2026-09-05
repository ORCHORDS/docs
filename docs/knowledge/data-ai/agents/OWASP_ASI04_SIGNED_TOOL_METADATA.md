# Signed Tool Metadata

## Purpose

Control profile for **OWASP ASI04: Agentic Supply Chain Vulnerabilities**.

## Control

Protect high-trust tool manifests or release metadata with verifiable signatures or attestations so catalog descriptions cannot be changed independently of publisher identity.

## Validation

Modify signed metadata and substitute an untrusted signer; verify admission fails before the tool becomes callable.

## Failure correction

Remove altered metadata, rotate compromised signing keys if necessary, and republish a verified manifest.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://slsa.dev/spec/v1.2/
- https://docs.sigstore.dev/policy-controller/overview/
