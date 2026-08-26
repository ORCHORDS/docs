# release-management-2026

**Issue:** A team releases software. The team debates release-please, semantic-release, Changesets, lerna version, manual. The team needs the 2026 reference for release automation.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 release tools compared

| Tool | Trigger | Versioning | Changelog | Publish |
|---|---|---|---|---|
| release-please | Conventional commits | Conventional Commits | Auto | GitHub releases, npm, etc. |
| semantic-release | Conventional commits | SemVer | Auto | npm, GitHub, etc. |
| Changesets | PR-time | Per-package | Auto per package | npm, etc. |
| lerna version | Manual | Fixed or independent | Optional | npm |
| Manual | Manual | Manual | Manual | Manual |

## The 5-step decision rule

1. **Single-package repo, want full automation** → release-please or semantic-release.
2. **Monorepo, independent per-package versions** → Changesets.
3. **Monorepo, fixed single version** → release-please with `release-type: node`.
4. **Need fine-grained control** → Changesets (you write the changeset with each PR).
5. **Legacy or unusual needs** → manual or custom script.

## The 5 best practices

1. **Conventional Commits** for commit-message-driven versioning.
2. **Changelog generated from commits**, not maintained by hand.
3. **PR-based changesets** for monorepos; reviewers see version impact at review time.
4. **Signed release tags** with Sigstore cosign.
5. **Release notes** with diff stat, contributors, breaking change callouts.

## Gotchas

- semantic-release requires a `GH_TOKEN` (or equivalent) with repo + write:packages scope.
- release-please creates "release PR"s that auto-merge when CI passes.
- Changesets file conflicts are common in busy monorepos; resolve in merge.
- npm provenance (--provenance) requires GitHub Actions OIDC; free for public repos.
- Pre-release versions (1.0.0-rc.1) need separate publish channels in some registries.

## Source URLs (verified 2026-08-10)

- https://github.com/googleapis/release-please
- https://semantic-release.gitbook.io/
- https://github.com/changesets/changesets
- https://www.conventionalcommits.org/
- https://docs.npmjs.com/generating-provenance-statements
