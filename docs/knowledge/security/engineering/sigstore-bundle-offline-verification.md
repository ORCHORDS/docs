---
title: "Sigstore Bundle Retention and Offline Verification"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# Sigstore Bundle Retention and Offline Verification

## Bundle contents and binding

A Sigstore bundle is a protobuf-defined envelope serialized as JSON that carries verification material. Bundle versions and media types matter: current clients may include a message signature or DSSE envelope, X.509 certificate chain, RFC 3161 timestamp verification data, and transparency-log entries with inclusion promise/proof. The authoritative schemas are in `sigstore/protobuf-specs`; do not invent a reduced internal “bundle” that drops fields.

The verifier still needs the artifact bytes or digest, the bundle, a trusted-root instance, an identity policy, and supported bundle semantics. For a blob, verification recomputes the digest covered by the message signature or DSSE payload. For DSSE it must verify the PAE construction and check `payloadType`; extracting JSON and verifying it as ordinary bytes is wrong.

```sh
cosign sign-blob --yes --bundle artifact.sigstore.json artifact.bin
cosign verify-blob --bundle artifact.sigstore.json \
  --certificate-oidc-issuer="$ISSUER" --certificate-identity="$IDENTITY" artifact.bin
```

## Offline evidence procedure

At release time retain artifact digest, unmodified bundle, bundle media type, verifier version, identity-policy version, and the exact trusted-root metadata. Perform online verification, disconnect Fulcio/Rekor/TSA access, and repeat using documented offline flags supported by the pinned client. Offline does not mean trust-free: the verifier must authenticate embedded log/checkpoint and timestamp evidence against retained roots.

Test altered artifact bytes, changed DSSE payload type, removed certificate, unknown log ID, invalid inclusion proof, wrong SAN, and a trust root that predates the log key. A current expired leaf certificate should still verify only if authenticated evidence establishes a signing time inside validity. Unsupported bundle versions must fail explicitly rather than silently ignore fields.

Store bundles beside immutable artifact digests with write-once retention. During client upgrades replay a corpus of historical valid and invalid bundles. Roll back the verifier version if semantic comparison differs, while keeping trust-root security updates separately assessed. Monitor bundle absence, schema rejection, identity mismatch, and online/offline result divergence.

## Sources

- [Bundle format](https://docs.sigstore.dev/about/bundle/)
- [Protobuf schemas](https://github.com/sigstore/protobuf-specs)
