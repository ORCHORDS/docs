# Agent Card Trust Pinning

## Purpose

Control profile for **OWASP ASI07: Insecure Inter-Agent Communication**.

## Control

Bind discovered agent capability metadata to an expected origin, identity, or trust policy so a look-alike card cannot silently replace a known peer.

## Validation

Present a same-name agent card from an untrusted origin and verify selection does not treat it as the pinned peer.

## Failure correction

Remove the poisoned discovery entry, restore trusted metadata, and tighten origin or identity constraints.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://a2a-protocol.org/dev/specification/
- https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/
