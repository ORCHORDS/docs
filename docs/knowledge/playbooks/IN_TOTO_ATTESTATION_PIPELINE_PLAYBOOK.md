# in-toto Attestation Pipeline Adoption Playbook

## Purpose

Stand up an end-to-end in-toto attestation pipeline that emits, signs, and verifies SLSA-conformant provenance and SBOM attestations across source, build, and deploy stages, so that every release is independently verifiable.

## Audience

Platform security engineers, build/release engineers, application teams adopting the new attestation pipeline.

## Pre-conditions

- in-toto-golang reference library pinned and installed (see `IN_TOTO_VERSION_GOVERNANCE.md`).
- A Sigstore Fulcio + Rekor instance (public or self-hosted) reachable from the CI cluster.
- SLSA L3 build infrastructure in place (Tekton or BuildKit-based builder).
- ProvenanceGate admission controller deployed in the workload cluster.

## Procedure

1. **Define the attestation model**: enumerate which attestations are emitted per stage. Default: SourceLink on PR merge, BuildSLSA on artifact publish, ProvenanceGate at admission.
2. **Configure predicate URIs**: pin the following predicate URIs in CI configuration: `https://slsa.dev/provenance/v1`, `https://spdx.dev/Document/v2.3`, `https://cyclonedx.org/bom/v1.6`, `https://openvex.dev/ns/v0.2.0`.
3. **Wire source stage**: at PR merge, run `in-toto-verify` to confirm the source link attestation includes a valid commit and a parent attestation.
4. **Wire build stage**: Tekton task `slsa-github-generator` emits the SLSA Build L3 provenance. Confirm the builder ID matches the pinned builder ID.
5. **Wire deploy stage**: ProvenanceGate admission controller validates each pod image against the expected provenance attestation. Reject if `predicate.materials` is missing the source repository URI.
6. **SBOM emission**: emit SPDX 2.3 at build time. Store in the Rekor transparency log alongside the provenance.
7. **VEX emission**: emit OpenVEX 0.2 entries for each known not-affected CVE.
8. **Verify in CI**: nightly job runs `slsa-verifier verify-image` against a sample of production images. Alert on failures.
9. **Document**: update `docs/security/attestation-model.md` with the predicate URIs, signing keys, and verification endpoints.

## Rollback

- Disable the ProvenanceGate admission controller (set `failurePolicy: Ignore`) and revert to the previous admission policy.
- Existing pods continue to run; only newly admitted pods are affected.
- Remove the Tekton task from the pipeline; existing artifacts retain their attestations.

## References

- in-toto specification — https://in-toto.io/
- SLSA generator — https://github.com/slsa-framework/slsa-github-generator
- Internal reference card: `IN_TOTO_VERSION_GOVERNANCE.md`.
