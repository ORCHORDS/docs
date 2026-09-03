# Dependency Digest Pinning

## Purpose

Control profile for **OWASP ASI04: Agentic Supply Chain Vulnerabilities**.

## Control

Pin security-sensitive agent components to immutable digests or equivalent content identities rather than mutable names alone.

## Validation

Move a tag or package label to different content and verify the approved deployment still resolves to the expected digest.

## Failure correction

Restore the approved digest, invalidate caches, and require review before accepting the new artifact.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://slsa.dev/spec/v1.2/
- https://csrc.nist.gov/pubs/sp/800/218/final
