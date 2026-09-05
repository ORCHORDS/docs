# Registry Namespace Collision Defense

## Purpose

Control profile for **OWASP ASI04: Agentic Supply Chain Vulnerabilities**.

## Control

Prevent public or lower-trust registries from satisfying names reserved for internal agent packages, plugins, skills, or tool definitions.

## Validation

Publish or simulate a same-name higher-version component in an untrusted source and verify resolution cannot select it.

## Failure correction

Pin the namespace to authoritative registries, remove the collided artifact, and inspect prior resolutions.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://slsa.dev/spec/v1.2/
- https://csrc.nist.gov/pubs/sp/800/218/final
