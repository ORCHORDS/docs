---
title: CNCF Notary v2 Artifact Attestation Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: Notary v2 (CNCF Incubating, https://github.com/notaryproject/notaryproject), client + signer + verifier components; in-toto SLSA provenance integration; OCI artifact binding via `referrers` tag API; complements COSIGN_VERSION_GOVERNANCE.md for non-image artifacts and SLSA provenance
---

# CNCF Notary v2 Artifact Attestation Version Governance

## Scope

This card governs how `orchords-docs` evaluates CNCF Notary v2 for signing and verifying arbitrary OCI artifacts and for storing in-toto SLSA provenance statements alongside those artifacts. Notary v2 supersedes the original Notary (TUF over Docker Content Trust) and is designed for the OCI distribution spec. Where cosign covers image signatures and keyless OIDC identity, Notary v2 covers broader attestation: SLSA provenance, SPDX SBOMs, and arbitrary payload attestations bound to an OCI artifact via the `application/vnd.oci.image.layer.v1.tar+gzip` referrer.

## Why this card exists

Notary v2 has three components (CLI client, signer, verifier) and three trust stores (local certificate store, remote trust store, trust policy). Drift between the CLI client and verifier produces a verification outcome that looks healthy but accepts unverified artifacts because the trust policy fallback is "skip". Drift between the signer and the certificate trust store produces silent signing failures during CI but successful signing at rest, which makes incident response impossible.

## Version support matrix (2026-09)

| Notary v2 | Released | EoL | Notes |
|---|---|---|---|
| 1.2.x | October 2024 | ~6 months after next minor | stable, OCI 1.1 referrers |
| 1.3.x | January 2025 | ~6 months after next minor | stable, trust policy v1.1 |
| 1.4.x | May 2025 | ~6 months after next minor | stable, SLSA provenance v1 |
| 1.5.x | September 2025 | ~6 months after next minor | stable, attestation envelope v0.2 |
| 1.6.x | February 2026 | ~6 months after next minor | stable, OCI 1.2 referrers |
| 1.7.x | July 2026 | current | stable, attestation envelope v0.3 |

Policy:

- Support the current minor and the previous minor (N-1).
- The trust policy schema version MUST match the verifier minor.
- Upgrade window: ≤ 3 months after a new Notary v2 minor release.

## Trust store and trust policy

- The trust store holds signing certificate roots and revocation lists; production MUST use a remote trust store reachable from the verifier.
- The trust policy is the only authoritative source for verification outcomes; `--insecure-skip-verify` is not a deployable configuration.
- A trust policy that does not specify `trustedIdentities`, `expiry`, or `authenticTimestamp` falls back to "skip", which silently accepts unverified artifacts.

## In-toto SLSA provenance integration

- Notary v2 stores in-toto SLSA provenance statements as OCI referrer artifacts bound by digest.
- The provenance predicate type (`https://slsa.dev/provenance/v1`) MUST be a literal string match; do not template it.
- Provenance produced by a `slsa-github-generator` release that is newer than the verifier's allowed list MUST be pinned to a matching Notary v2 verifier.

## Compatibility notes

- Notary v2 verifiers are deployed as sidecars in admission controllers (e.g., `ratify` on Kubernetes) and as standalone CLI in CI.
- Mixing Notary v2 with cosign is supported; the verification policy SHOULD declare which artifacts require which signer (image signatures by cosign, SBOMs and provenance by Notary v2).
- Avoid the original Docker Content Trust (DCT) tooling path; it shares no trust store, key material, or policy format with Notary v2.

References: `https://github.com/notaryproject/notaryproject`, `https://github.com/notaryproject/specification`, `https://github.com/notaryproject/notation`, `https://github.com/notaryproject/notation-action`, `https://github.com/deislabs/ratify`, `https://slsa.dev/`.
