# Plugin SBOM Requirement

## Purpose

Control profile for **OWASP ASI04: Agentic Supply Chain Vulnerabilities**.

## Control

Require a software bill of materials or equivalent dependency inventory for executable agent plugins and extensions when supply-chain risk warrants it.

## Validation

Submit components with complete, incomplete, and stale inventories; verify policy can distinguish their admission state.

## Failure correction

Block or downgrade the component, regenerate the inventory from a trusted build, and investigate undisclosed dependencies.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://slsa.dev/spec/v1.2/
- https://csrc.nist.gov/pubs/sp/800/218/final
