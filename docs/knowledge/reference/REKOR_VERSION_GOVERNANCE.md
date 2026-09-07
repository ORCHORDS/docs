---
title: Sigstore Rekor Transparency Log Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: Sigstore project (https://www.sigstore.dev/); CNCF graduated Rekor 1.3.x (March 2024), 1.4.x (July 2024), 2.0.x (October 2024), 2.1.x (February 2025), 2.2.x (July 2025), 2.3.x (December 2025), 2.4.x (April 2026), 2.5.x (August 2026); Rekor v2 ("rekor-tiles") immutable, append-only tile-based log
---

# Sigstore Rekor Transparency Log Version Governance

## Scope

This card governs how `orchords-docs` evaluates Sigstore Rekor, the transparency log for signed attestations used by Cosign, gitsign, and the Fulcio certificate authority. It is the reference input for any KB card that cites signature inclusion proofs, log monitoring, log sharding, or Rekor v2 ("rekor-tiles") migration.

## Why this card exists

Rekor is the immutable, append-only log that gives Cosign and Fulcio entries their verifiability. A KB card that signs with Cosign but does not bind to a Rekor version, shard, and inclusion-anchoring strategy produces signatures that cannot be independently verified by third parties and silently breaks when the Rekor v1 → v2 migration completes. Without a version pin, monitoring toolchains miss entries, and log-shard health stops being actionable.

## Version support matrix (2026-09)

| Rekor | Released | EoL | Notes |
|---|---|---|---|
| 2.1.x | February 2025 | ~6 months after next minor | stable, classic backend, v1 schema |
| 2.2.x | July 2025 | ~6 months after next minor | stable, log sharding GA |
| 2.3.x | December 2025 | ~6 months after next minor | stable, required for STIX 2.1 export |
| 2.4.x | April 2026 | ~6 months after next minor | stable, rekor-tiles beta |
| 2.5.x | August 2026 | current | stable, rekor-tiles GA, sharded checkpoint |

Policy:

- Support the current minor and the previous minor (N-1).
- Rekor-tiles ("v2") is the recommended backend for new deployments.
- The Rekor client must pin the log ID, not just the URL, to avoid cross-shard verification confusion.
- Upgrade window: ≤ 3 months after a new minor release.
- Rekor v1 classic backend reaches end-of-life 2027-06-30; migrate to rekor-tiles before then.

## Inclusion proof and monitoring guidance

- Always request an inclusion proof at signing time; treat "signed but no inclusion proof" as an incomplete signature.
- Pin the Rekor public key (PEM) in the consumer trust store; rotate trust on log key rotation events only.
- For high-volume CI clusters, deploy a Rekor witness or local mirror to avoid rate-limiting against the public log.
- Monitor Rekor checkpoint lag and signed-note tree size; alert on either exceeding a documented threshold.
- Run periodic `rekor-cli verify` against historical entries to detect post-hoc log tampering.

## Compatibility notes

- Cosign references (Cosign 2.x+ and Cosign 3.x) follow Rekor within ±1 minor.
- Fulcio root transitions require coordinated Rekor checkpoint observation.
- gitsign uses Rekor for commit signature inclusion; a Rekor outage degrades gitsign to local-only signing.
- The Rekor STIX 2.1 export profile requires Rekor 2.3.x or later.

References: `https://www.sigstore.dev/`, `https://github.com/sigstore/rekor`, `https://github.com/sigstore/rekor-tiles`, `https://github.com/sigstore/sigstore-go`, Rekor v2 I-D `draft-davidson-sigstore-rekor-v2`.
