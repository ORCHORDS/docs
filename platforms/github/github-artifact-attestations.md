# github-artifact-attestations

**Issue:** Build outputs can be copied or replaced after CI unless consumers can verify provenance.
**Date:** 2026-08-26
**Status:** documented
**Source:** https://docs.github.com/en/actions/concepts/security/artifact-attestations

## Context
GitHub artifact attestations create signed provenance claims for build artifacts. GitHub documents that attestations can bind an artifact to its workflow, repository, commit SHA, triggering event, environment, and other OIDC-derived build information.

## Pattern
Use attestations for software people actually consume:
- release binaries
- container images
- downloadable packages
- manifests containing hashes of distributed artifacts

Do not generate attestations merely for every transient test build. Provenance is useful only when consumers actually verify it.

## Workflow permissions
A build-provenance workflow generally needs:

```yaml
permissions:
  id-token: write
  contents: read
  attestations: write
```

Generate the attestation only after the artifact exists. For containers, attest the immutable image digest rather than a mutable tag.

## Verification
Consumers can verify supported artifacts with GitHub CLI, for example:

```bash
gh attestation verify PATH_TO_ARTIFACT -R OWNER/REPO
```

Verification should be part of the release or deployment trust decision, not an optional afterthought.

## Security boundaries
- An attestation proves provenance information; it does not prove the artifact is vulnerability-free.
- Protect the workflow and reusable build logic that produces the artifact.
- Prefer immutable digests for container subjects.
- Treat attestation verification policy separately from malware, SAST, dependency, or runtime security controls.

## Plan availability
GitHub documentation states that artifact attestations are available on current plans, but private/internal repository support requires GitHub Enterprise Cloud. Check plan applicability before designing a private-repository enforcement workflow around the feature.

## Related
- `github-oidc-cloud-auth.md`
- `github-actions-security-hardening.md`
- `slsa-supply-chain.md`
