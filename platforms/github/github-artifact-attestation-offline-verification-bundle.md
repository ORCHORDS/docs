# GitHub artifact-attestation offline verification bundle

**Issue:** Offline attestation verification needs more than the artifact and a copied signature. The verifier must receive the attestation bundle, an appropriate Sigstore trusted-root export, and a compatible GitHub CLI while accepting that an isolated environment cannot learn about trust-root changes or revocations after export.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- On a connected staging system, download the attestation bundle for the exact artifact and repository with `gh attestation download`.
- Generate a fresh trusted-root file with `gh attestation trusted-root` for every import of newly signed material.
- Transfer the artifact, bundle, trusted root, GitHub CLI package, and their manifest through an authenticated, malware-scanned import process.
- Pin and independently verify the GitHub CLI version before it enters the offline environment.
- Bind the verification policy to the expected repository or owner, artifact digest, workflow identity, predicate type, and any required signer conditions.
- Store the import time, source, file digests, verifier version, command, policy, and complete result as evidence.
- Keep a controlled re-verification process for material whose trust decision must survive root rotation or revocation events.

## Implementation and tests

On the offline system, verify the artifact with `gh attestation verify`, the downloaded `--bundle`, and `--custom-trusted-root`, while supplying the expected repository. Fail closed on any missing file, digest mismatch, identity mismatch, unsupported predicate, malformed JSONL, or verifier error.

Test a valid set and then tamper separately with the artifact, bundle, trusted root, repository identity, and manifest. Test an older trusted root against newly signed material and a newly exported root against older material. Confirm the importer cannot silently overwrite previously approved evidence.

## Gotchas and applicability

GitHub documents that the trusted-root file has no built-in expiration. Material signed before the root export can continue to verify, while later material depends on subsequent key rotation; the offline verifier also cannot know about revocations since the last export. A cryptographically valid attestation proves the asserted provenance under the selected policy, not that the source, build, or artifact is vulnerability-free.

Offline transfer rules and retention may be subject to organizational or regulatory controls.

## Official sources

- [GitHub Docs: Verifying attestations offline](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/verify-attestations-offline)
- [GitHub Docs: Using artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations)
