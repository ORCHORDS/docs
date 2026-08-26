# GitHub artifact attestations and SLSA Build Level 3

**Date:** 2026-08-26
**Status:** documented
**Sources:**
- https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/increase-security-rating
- https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations

## Context

GitHub documents a pattern using reusable workflows plus artifact attestations to support SLSA v1.0 Build Level 3 requirements.

## Pattern

- Centralize the build in a controlled reusable workflow.
- Generate provenance attestations for the artifacts produced by that workflow.
- Verify the attestation and expected builder identity before trusting a release artifact.
- Keep release consumers aware that an attestation proves recorded build provenance; it is not a blanket statement that the source or artifact is vulnerability-free.

## Verification

For each protected artifact:

1. verify the attestation using GitHub-supported verification tooling;
2. confirm the repository/workflow identity matches the expected builder;
3. reject an artifact with missing or mismatched provenance;
4. ensure the build path cannot be silently replaced with an unreviewed workflow;
5. retain enough release evidence to reproduce the verification decision.

## Boundary

Do not claim a project "is SLSA Level 3" merely because attestations exist. The applicable SLSA requirements and the complete build system must actually satisfy the claimed level.
