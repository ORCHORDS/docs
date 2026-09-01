---
title: "Rekor Inclusion and Transparency Monitoring"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# Rekor Inclusion and Transparency Monitoring

## Transparency semantics

Rekor records hashed, signed supply-chain metadata in an append-only Merkle tree. An inclusion promise (signed entry timestamp, SET) is a log signature over the canonicalized entry; an inclusion proof supplies the leaf hash, tree size, root hash, and sibling hashes needed to recompute the root. A checkpoint signs a tree state. Inclusion proves an entry is in that state. Consistency proofs between tree sizes demonstrate append-only growth; neither proves that the signer was authorized or the artifact was safe.

A verifier binds the Rekor entry body to the expected artifact digest and signature/certificate, verifies the log ID/key, checks the SET or inclusion proof, and authenticates the checkpoint. `integratedTime` is the log's observation time, not a user-controlled release date and not evidence that source existed earlier. `logIndex` is location, not identity; retain entry UUID/body hash and log identity.

## Monitoring and failure tests

Use the Rekor API or supported `rekor-cli`/cosign version to retrieve the entry and inclusion evidence. Persist the raw canonical entry, UUID, index, integrated time, tree size, root hash/checkpoint, log ID, and verification output. Compare checkpoints observed from independent networks or a witness mechanism when available. Alert on root rollback, inconsistent tree sizes, unknown log IDs, invalid proofs, and signatures missing required transparency evidence.

Negative tests alter one audit-path hash, tree size, entry body digest, certificate, SET, and checkpoint signature. Test log outage explicitly: policy may queue release, use already embedded bundle evidence, or invoke an approved emergency path; it must not treat “could not query” as “entry valid.” Public entries are durable and observable, so never submit secrets or unnecessary private names.

If a log key rotates, update authenticated trusted-root metadata and replay historical bundles with the old key retained for their validity interval. Rollback restores the previous trusted root only if it has not been revoked; otherwise pause verification and investigate rather than accepting an unknown log.

## Sources

- [Rekor overview](https://docs.sigstore.dev/logging/overview/)
- [Rekor API/project](https://github.com/sigstore/rekor)
