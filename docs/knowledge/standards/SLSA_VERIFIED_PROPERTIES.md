# SLSA Verified Properties

## Purpose

SLSA v1.2 introduces Verified Properties for software-supply-chain controls that are useful to express but do not fit cleanly into a SLSA level or track. A verifier can include these named properties in the `verifiedLevels` field of a Verification Summary Attestation (VSA) when the property-specific requirements have been met.

The current approved v1.2 specification defines two Verified Properties:

- `SLSA_SOURCE_TWO_PARTY_REVIEWED`; and
- `SLSA_BUILD_REPRODUCED`.

## Two-party-reviewed source

`SLSA_SOURCE_TWO_PARTY_REVIEWED` indicates that the source associated with the artifact was reviewed by two trusted persons in accordance with the Source track's two-party-review requirements.

The property can be asserted at any Source level where the source-control system can make the claim. It must not be used as shorthand for Source L4 unless all Source L4 requirements are also met.

## Reproduced build

`SLSA_BUILD_REPRODUCED` indicates that the artifact was reproduced by two or more builders.

The current specification requires build provenance from two or more **independently operated Build Platforms** trusted by the VSA issuer. Rebuilding twice on the same build platform is useful reproducibility evidence but does not satisfy this Verified Property.

## Consumer pattern

1. Verify the VSA issuer and subject before using any Verified Property.
2. Check the exact property string rather than relying on human-readable labels.
3. Confirm the issuer's policy and evidence meet the property's current SLSA requirements.
4. Do not infer a higher Source or Build level merely because a Verified Property is present.
5. For `SLSA_BUILD_REPRODUCED`, confirm the builders are independently operated rather than two executions of one platform.
6. Preserve the VSA and policy reference with the artifact digest so the assertion can be re-evaluated later.

## Producer and verifier guidance

Verified Properties should be emitted only when the verifier has sufficient evidence to make the named claim. If an internal control resembles a SLSA property but does not meet the specification's exact requirements, describe the internal control in different terms instead of reusing the reserved SLSA property name.

## Failure modes

- Treating two approvals as Source L4 without satisfying the rest of the Source-track requirements overstates assurance.
- Calling two same-platform rebuilds `SLSA_BUILD_REPRODUCED` conflicts with the independent-build-platform requirement.
- Accepting a Verified Property from an untrusted VSA issuer defeats the trust model.
- Using a retired release-candidate page instead of the approved v1.2 specification can introduce stale requirements.

## Sources

- SLSA v1.2 — Verified Properties: https://slsa.dev/spec/v1.2/verified-properties
- SLSA v1.2 — Verification Summary Attestation: https://slsa.dev/spec/v1.2/verification_summary
- SLSA v1.2 — Source requirements: https://slsa.dev/spec/v1.2/source-requirements

## Scope note

This article explains the semantics of SLSA Verified Properties. It does not claim that any artifact, source repository, review process, or build system qualifies for either property.