# Tool Registry Provenance

## Purpose

Control profile for **OWASP ASI04: Agentic Supply Chain Vulnerabilities**.

## Control

Record where each tool or plugin definition came from, who published it, which version is in use, and the integrity identifier used for admission.

## Validation

Introduce a tool with missing or conflicting provenance and verify it cannot enter the trusted catalog silently.

## Failure correction

Quarantine the component, restore a verified version, and correct registry admission rules.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://slsa.dev/spec/v1.2/
- https://csrc.nist.gov/pubs/sp/800/218/final
