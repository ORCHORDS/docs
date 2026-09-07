---
title: Sigstore Cosign Image and Signature Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: Sigstore cosign (https://github.com/sigstore/cosign), part of CNCF Sigstore (Graduated 2023); cosign v2.x (keyful and keyless via Fulcio + Rekor transparency log); bundled with `policy-controller` (Sigstore Policy Controller) for Kubernetes admission; complements NOTARY_V2_VERSION_GOVERNANCE.md for broader artifact attestation
---

# Sigstore Cosign Image and Signature Version Governance

## Scope

This card governs how `orchords-docs` evaluates Sigstore cosign for OCI image signing and verification. Cosign is the signing client; Sigstore's transparency log (Rekor), root-CA-issued short-lived signing certificates (Fulcio), and the key-encryption client (`cosign encrypt`) round out the family. A KB card that cites "cosign verified" without binding to cosign version, signature payload layout, and Rekor index version produces an admission pipeline that accepts unsigned images because the verify step falls through to a default-permit.

## Why this card exists

Cosign is the de-facto image signer across the Kubernetes and supply-chain ecosystem. It supports keyful signing with a self-managed key pair, keyless signing using an OIDC identity bound to a Fulcio-issued short-lived certificate, and key-encryption for secrets-as-artifacts. Version drift between cosign and `policy-controller` (Sigstore Policy Controller) breaks admission: the controller cannot read a payload produced by a newer cosign minor, or vice versa.

## Version support matrix (2026-09)

| cosign | Released | EoL | Notes |
|---|---|---|---|
| v2.3.x | October 2024 | ~6 months after next minor | stable, Rekor v2 client support |
| v2.4.x | January 2025 | ~6 months after next minor | stable, keyless with ambient OIDC |
| v2.5.x | April 2025 | ~6 months after next minor | stable, `cosign attest` first stable |
| v2.6.x | August 2025 | ~6 months after next minor | stable, OIDC for non-image artifacts |
| v2.7.x | February 2026 | ~6 months after next minor | stable, bundle format version 0.2 |
| v2.8.x | August 2026 | current | stable, bundle format version 0.3 (breaking) |

Policy:

- Support the current minor and the previous minor (N-1).
- Bundle format version is tracked separately; pin both cosign and `policy-controller` so they read the same bundle version.
- Upgrade window: ≤ 3 months after a new cosign minor release.

## Keyful vs keyless signing

- Keyful: signing key is stored in a KMS, HSM, or encrypted file. The signature payload is self-contained; verification does not require Rekor.
- Keyless: the signature is bound to an OIDC identity (issuer + subject + SAN) and an Rekor entry. Verification requires both the certificate chain (Fulcio root) and the Rekor index entry.
- Production keyless pipelines SHOULD pin the Fulcio root CA certificate and use a published transparency log mirror (`https://rekor.sigstore.dev`).

## Signature payload evolution

- v1 payload: `{"payload":"<base64>","signature":"<base64>"}` — used for image and blob signatures.
- v2 payload (bundles): a JSON envelope with `mediaType`, `verificationMaterial`, and `dsseEnvelope`. v2 bundles are required for `policy-controller` and for cross-ecosystem consumers (in-toto, Kyverno `imageSignature` policy plugins).
- A signature produced by cosign v2.8.x with bundle v0.3 cannot be read by `policy-controller` < v0.10 — pin to compatible minors.

## Compatibility notes

- The `policy-controller` CRD `ClusterImagePolicy` MUST be reviewed against the policy-controller minor that ships the fields used; see the `policy-controller` release notes.
- Kyverno image verification policies that consume cosign signatures SHOULD be versioned alongside `cosign verify-image --check-claims`.
- Avoid mixing cosign versions across CI and the admission webhook; a CI verifier that is one minor ahead of the controller causes hard admission failures on every signature.

References: `https://github.com/sigstore/cosign`, `https://docs.sigstore.dev/`, `https://github.com/sigstore/policy-controller`, `https://www.cncf.io/projects/sigstore/`, `https://github.com/sigstore/rekor`.
