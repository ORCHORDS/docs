# OCI referrers for SBOM, signature, and provenance discovery

**Issue:** SBOMs, signatures, and provenance can be published beside a container image yet become undiscoverable, copied without their subject, or evaluated against a mutable tag rather than the artifact digest.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Model supply-chain evidence as OCI artifacts related to an immutable subject digest. Use the OCI image manifest `subject` descriptor and Distribution Specification referrers API so consumers can discover evidence from the artifact they are actually admitting.

## Controls

1. Build and push the image, then resolve its manifest digest.
2. Generate evidence from that exact artifact. Give each artifact an explicit registered or vendor media type.
3. Set the evidence manifest's `subject` to the image manifest or index descriptor.
4. Query `/v2/<name>/referrers/<digest>`; filter by `artifactType` only when supported and check the `OCI-Filters-Applied` response header.
5. Support the specification's referrers-tag-schema fallback when the endpoint returns 404.
6. Verify every returned descriptor's digest and size before use.
7. Copy the subject and required referrers together during promotion; fail closed when required evidence is absent or invalid.
8. Define policy for multiple or superseding attestations instead of selecting the newest blindly.

## Verification

- Push a test subject with SBOM and signature referrers and enumerate both by digest.
- Exercise a registry without the API and validate fallback behavior.
- Copy between registries and compare subject/referrer digests.
- Inject unknown artifact types and confirm clients preserve or safely ignore them as specified.
- Mutate a tag and confirm admission still verifies the pinned digest.

## Gotchas

A `subject` relation is a weak association, not proof of authenticity. Verify signatures, issuer identity, claims, and subject digest. Tags are mutable. Registry garbage collection and copy tools may omit referrers unless explicitly tested.

## Sources

- [OCI Image Manifest Specification](https://github.com/opencontainers/image-spec/blob/main/manifest.md)
- [OCI Distribution Specification: referrers](https://github.com/opencontainers/distribution-spec/blob/main/spec.md)
- [OCI Descriptor Specification](https://github.com/opencontainers/image-spec/blob/main/descriptor.md)
