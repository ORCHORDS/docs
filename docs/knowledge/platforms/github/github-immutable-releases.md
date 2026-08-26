# GitHub immutable releases for actions

**Date:** 2026-08-26
**Status:** documented
**Source:** https://docs.github.com/en/actions/how-tos/create-and-publish-actions/using-immutable-releases-and-tags-to-manage-your-actions-releases

## Context

GitHub supports immutable releases for repositories that publish Actions. Once a release is made immutable, its release assets and release tag cannot be changed through normal release mutation.

## Release pattern

For an Action repository:

- Use a release-specific tag such as `v1.0.0` for a version that should remain unchangeable.
- Keep moving major or minor convenience tags such as `v1` or `v1.1` separate from an immutable GitHub release when those tags need to advance to newer compatible commits.
- Validate the release candidate before creating the immutable release.
- Document which references consumers should pin: immutable release tags, moving major tags, or commit SHAs.

## Why this matters

Mutable tags can be useful for compatibility channels, but they are not the same trust property as an immutable release. Consumers that need stronger reproducibility should use a reference whose intended mutability is explicit.

## Verification

1. Confirm immutable releases are enabled where the repository policy requires them.
2. Confirm release-specific tags map to the intended commit.
3. Confirm moving compatibility tags are not accidentally attached to releases that are intended to be immutable.
4. Verify downstream workflow examples describe whether the reference is mutable or immutable.

## Gotchas

- A normal Git tag can be force-moved; treating every tag as immutable is incorrect.
- GitHub's own guidance separates immutable release-specific tags from moving major/minor compatibility tags.
- Release immutability does not replace artifact provenance or attestation checks.

## Related

- `github-artifact-attestations.md`
