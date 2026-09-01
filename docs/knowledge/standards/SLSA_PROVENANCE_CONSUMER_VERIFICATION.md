# SLSA Provenance Consumer Verification

## Purpose

SLSA provenance provides verifiable information about where, when, and how a software artifact was produced. The current SLSA specification is version 1.2. Consumers should use provenance as input to an explicit allow/deny decision rather than treating the mere presence of an attestation as proof that an artifact is trustworthy.

## Current SLSA context

SLSA v1.2 separates provenance concepts across tracks. Build provenance traces a build output back to the source and build process that produced it, while source provenance covers source revisions and source-control change-management properties.

The in-toto predicate URI `https://slsa.dev/provenance/v1` identifies the major-version-compatible build provenance format. SLSA documents that backwards-incompatible changes require a predicate major-version change, while compatible minor changes can retain the same predicate URI.

## Consumer verification pattern

1. Verify the attestation envelope and signer using the mechanism defined by the provenance distribution system.
2. Confirm the attestation subject digest matches the artifact bytes that will actually be consumed.
3. Confirm the predicate type is an expected SLSA provenance type and parse it according to the applicable current specification.
4. Compare `builder.id` against an allowlist of build platforms or builder identities that the consuming organization trusts.
5. Accept only signer–builder combinations that are expected for that build platform.
6. Verify the `buildType` is understood and approved for the artifact class being consumed.
7. Inspect `externalParameters` and reject unexpected or policy-disallowed values that could materially change the build.
8. Validate relevant resolved dependencies, source revisions, and build inputs when the consumer's policy requires those constraints.
9. Treat unknown extension fields according to SLSA parsing rules; extensions must not be allowed to silently weaken an otherwise deny decision.
10. Record the policy decision together with the artifact digest and provenance identity so the verification can be reproduced later.

## Builder identity

SLSA defines `builder.id` as the identity of the build platform trust boundary. The identifier should represent the transitive set of systems and actors that a consumer must trust to execute the build and produce accurate provenance.

Different operational modes with materially different security properties should not be collapsed into one indistinguishable builder identity. Consumers should understand what a builder ID claims before relying on it.

## External parameters

External parameters are inputs controlled outside the trusted build platform. SLSA expects downstream consumers to verify them because they may influence what is built. A useful policy should therefore define what parameters are permitted instead of accepting arbitrary values merely because the provenance is signed.

Examples can include repository/ref inputs, build entry points, configuration choices, or other caller-controlled values defined by the build type.

## Resolved dependencies

Where provenance includes resolved dependencies, verify the identifiers and digests relevant to the consumer's threat model. The presence of a dependency list is not equivalent to completeness unless the applicable SLSA level and build-platform guarantees establish the required completeness.

## Failure modes

- Verifying only the signature without matching the artifact digest can validate provenance for a different artifact.
- Trusting any valid signer instead of an expected signer–builder pair can admit provenance from an unintended build system.
- Accepting arbitrary `externalParameters` can let a trusted builder produce an unapproved artifact configuration.
- Treating builder IDs as self-explanatory without understanding their trust boundary can overstate assurance.
- Assuming every dependency is captured can exceed the completeness guarantees of the build platform.
- Using retired SLSA version pages as the current normative reference can cause version-status errors.

## Sources

- SLSA v1.2 — Provenance: https://slsa.dev/spec/v1.2/provenance
- SLSA v1.2 — Verifying artifacts: https://slsa.dev/spec/v1.2/verifying-artifacts
- SLSA v1.2 — Build provenance: https://slsa.dev/spec/v1.2/build-provenance

## Scope note

This article describes consumer-side verification principles. It does not claim that a particular artifact, build platform, or repository satisfies a SLSA level.