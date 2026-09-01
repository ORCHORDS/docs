# SLSA Source Provenance Verification

## Purpose

SLSA v1.2 includes a Source track for evaluating how a source revision was created and what source-control protections were in force. Source provenance and Source Verification Summary Attestations (VSAs) can carry evidence about those properties, but the evidence is useful only when a consumer verifies it against an expected source-control trust root and policy.

## Source-track context

SLSA Source levels progress from version control through history/provenance and continuous technical controls to two-party review. At Source L3 and above, source-control systems can issue detailed provenance about the process that produced a revision. Source VSAs can summarize prior verification results for easier consumption.

## Verification pattern

1. Identify the source revision by immutable revision digest or identifier.
2. Verify that the VSA or source provenance actually applies to that revision.
3. Establish which source-control-system identities are trusted and the maximum Source level each is trusted to assert.
4. Compare the VSA's claimed source properties and level with the consuming organization's expectations.
5. Where higher assurance is required, inspect the underlying source provenance rather than relying only on the summary attestation.
6. Verify that technical controls were continuously enforced for the protected named reference when the claimed Source level requires that property.
7. Treat gaps in control continuity as a reset or downgrade condition rather than assuming later enforcement retroactively protects earlier revisions.
8. Record the verification result with the revision identifier and evidence identity.

## Two-party review

SLSA Source L4 requires two trusted persons to agree to changes before submission to protected branches. Review applies to the final revision: material changes after approval must also be reviewed.

The two trusted persons can be the uploader plus a distinct reviewer or two distinct reviewers. Review context matters; moving reviewed content into another protected context can require another review depending on the source-control workflow.

## Source VSAs

A Source VSA summarizes a determination made by a verifier that has enough evidence to assess the source revision. Consumers should not accept arbitrary VSA issuers. The VSA issuer and source-control-system root of trust must be part of the consumer's configured trust policy.

The VSA subject digest should include the revision identifier. Human-readable subject URIs are useful for investigation but should not substitute for immutable identifiers in policy decisions.

## Failure modes

- Trusting a source-level claim without validating the issuer can accept fabricated assurance.
- Matching by repository URL alone instead of revision digest can verify the wrong revision.
- Assuming branch protection existed continuously when it was temporarily disabled can overstate Source L3 evidence.
- Accepting review of an earlier patchset after unreviewed changes were added violates the intent of final-revision review.
- Treating source provenance as equivalent to build provenance mixes different SLSA trust questions.

## Sources

- SLSA v1.2 — Source: Verifying source: https://slsa.dev/spec/v1.2/verifying-source
- SLSA v1.2 — Source requirements: https://slsa.dev/spec/v1.2/source-requirements
- SLSA v1.2 — Verified Properties: https://slsa.dev/spec/v1.2/verified-properties

## Scope note

This article describes verification of SLSA Source-track evidence. It does not claim that any repository, source-control system, or revision satisfies a SLSA Source level.