---
title: "Sigstore Keyless Signing Identity Policy"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# Sigstore Keyless Signing Identity Policy

## Certificate and identity semantics

Sigstore keyless signing exchanges an OIDC identity for a short-lived Fulcio signing certificate. The certificate's SAN and issuer-related extensions carry identity claims; verification must constrain both expected issuer and expected identity. Trusting the Fulcio root and seeing a valid signature only proves that some accepted identity signed. For CI, policy should bind repository, workflow, ref, trigger, and environment claims exposed by the supported client and issuer.

Cosign verification inputs are: artifact digest or blob; signature or Sigstore bundle; Fulcio trust root/intermediates; Rekor public key or current trusted-root metadata; current time or authenticated signing-time evidence; and identity policy. A representative command is:

```sh
cosign verify registry.example/app@sha256:... \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  --certificate-identity=https://github.com/acme/app/.github/workflows/release.yml@refs/tags/v2.4.0
```

Use the exact identity syntax emitted by the current certificate profile and pin a tested cosign version. Regex identity matching must be anchored; broad repository-prefix expressions can authorize pull-request or branch workflows unintentionally.

## Trust-root and rollout controls

Sigstore clients increasingly consume signed trusted-root metadata containing Fulcio, Rekor, and timestamp authority material. Archive the trusted-root version used for a decision and test root rotation. A certificate expiring after minutes remains verifiable later only when trusted signing-time/transparency evidence proves it was valid when signed.

Negative tests sign from a fork, branch, pull request, renamed workflow, reusable workflow caller, and unauthorized environment. Also alter the digest, issuer, SAN, and bundle. Block immutable digests, never mutable tags alone. If identity federation is unavailable, fail the release or use a separately governed emergency signer; do not disable identity checks. Record certificate claims, bundle digest, trust-root version, policy ID, and verifier output. Alert on unseen issuer/SAN pairs and signing from unprotected refs.

## Sources

- [Sigstore keyless](https://docs.sigstore.dev/cosign/signing/signing_with_blobs/)
- [Verification](https://docs.sigstore.dev/cosign/verifying/verify_blob/)
