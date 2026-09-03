# Publisher Identity Verification

## Purpose

Control profile for **OWASP ASI04: Agentic Supply Chain Vulnerabilities**.

## Control

Verify the publisher or build identity associated with agent tools, models, plugins, and policy bundles before treating provenance claims as trusted.

## Validation

Present valid artifacts from an unexpected publisher and look-alike publisher identities; verify trust policy rejects them.

## Failure correction

Revoke the untrusted component, correct issuer or subject constraints, and review deployments admitted under weak matching.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://slsa.dev/spec/v1.2/
- https://docs.sigstore.dev/policy-controller/overview/
