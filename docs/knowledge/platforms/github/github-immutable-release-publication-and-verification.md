# GitHub immutable release publication and verification

**Issue:** A published tag or release asset can be replaced after downstream users have trusted it, breaking reproducibility and creating a software-supply-chain attack path.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Enable GitHub release immutability for repositories that distribute versioned artifacts. Publish only after all assets, notes, checksums, and attestations are final, then verify the release from a clean consumer context.

GitHub documents that immutable releases lock the associated tag and assets. Publication also generates a release attestation containing the tag, commit SHA, and release assets. Enforcement applies to future releases, so older releases require separate risk treatment.

## Publication flow

1. Build once from a reviewed commit and retain the commit SHA and artifact digests.
2. Create a draft release.
3. Upload the complete asset set to the draft. Generate checksums from the exact uploaded build outputs.
4. Run malware, license, provenance, signature, and installability checks before publication.
5. Have an independent reviewer compare the draft tag, commit, assets, and release notes.
6. Publish the draft, making it immutable.
7. Verify the release and representative downloaded assets with supported GitHub CLI verification commands.
8. Record verification output and the release URL in deployment evidence.

## Verification

- Confirm the release page marks the release immutable.
- Run `gh release verify RELEASE-TAG`.
- Download a release asset into a clean workspace and run `gh release verify-asset RELEASE-TAG ARTIFACT-PATH`.
- Confirm deployment automation consumes the immutable tag/digest and does not rebuild source archives.
- Attempt the process in a test repository to demonstrate that a published tag and asset cannot be altered.

## Gotchas

- GitHub notes that release verification does not verify on-demand source-code zip or tar archives.
- Immutability is not retroactive.
- Deleting an immutable release is a governance event, not a normal editing workflow.
- Do not publish partially assembled releases; use drafts until complete.
- Immutability proves consistency with publication, not that the code is vulnerability-free.

## Sources

- [GitHub Docs: Immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)
- [GitHub Docs: Preventing changes to releases](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes)
- [GitHub Docs: Verifying release integrity](https://docs.github.com/en/enterprise-cloud@latest/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/verify-release-integrity)
