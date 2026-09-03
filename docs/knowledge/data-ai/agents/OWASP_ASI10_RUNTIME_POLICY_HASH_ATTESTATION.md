# Runtime Policy Hash Attestation

## Purpose

Control profile for **OWASP ASI10: Rogue Agents**.

## Control

Record a cryptographic content identity for security-critical policy loaded by an agent runtime so incident evidence can distinguish exactly which rules were active.

## Validation

Load two policy bundles with the same label but different content and verify telemetry or inventory reports distinct identities.

## Failure correction

Quarantine unrecognized policy content, restore the approved bundle, and investigate unauthorized changes.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
