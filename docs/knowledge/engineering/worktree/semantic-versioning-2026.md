# semantic-versioning-2026

**Issue:** A team ships an SDK. They release 1.0.0. A user updates and the API breaks. The team says "we didn't promise anything." The user says "you removed the only function I called." The team had no versioning discipline.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Semantic Versioning 2.0.0 (SemVer) is the 2014 standard. The 2026 production pattern is SemVer + Conventional Commits + automated version bumping, with a documented public API.

## Root cause

Versions like 1.0.0 carry meaning: MAJOR.MINOR.PATCH. Without discipline, breaking changes sneak into minor versions. Without an automated tool, the version bump is forgotten.

## The SemVer 2.0.0 rules

Given a version MAJOR.MINOR.PATCH:

1. **MAJOR** — incompatible API changes
2. **MINOR** — add functionality (backwards-compatible)
3. **PATCH** — bug fixes (backwards-compatible)
4. **Pre-release** — append `-alpha.1`, `-beta.2`, `-rc.1` (lower than the version without)
5. **Build metadata** — append `+20130313144700` (ignored in precedence)

The 3 rules. The 2 clarifications.

## The 5 breaking changes that count as MAJOR

1. **Removing a public function or method**
2. **Changing a function signature** (renaming parameters in a way that breaks callers, changing return type)
3. **Changing behavior in a backwards-incompatible way** (e.g., a function that returned `null` now throws)
4. **Removing a public type or interface**
5. **Changing license terms** (in some projects)

The 2026 common dispute: is removing a deprecated function a breaking change? Convention says no if it was deprecated for at least one minor version with a clear migration path.

## The Conventional Commits → SemVer bridge

Conventional Commits 1.0.0 (October 2022) defines commit message types that map to SemVer bumps.

| Commit type | SemVer bump |
|---|---|
| `feat:` | MINOR |
| `fix:` | PATCH |
| `feat!:` or `BREAKING CHANGE:` footer | MAJOR |
| `chore:`, `docs:`, `refactor:`, `test:`, `ci:`, `build:`, `perf:` | PATCH (default) or no bump (configurable) |

Automated tools (release-please, semantic-release) read the commit log, derive the next version, generate a changelog, and create a release.

## The 3 release automation tools

| Tool | Best for | Approach |
|---|---|---|
| semantic-release | JS/TS, monorepo-friendly | fully automated, GitHub releases + npm publish |
| release-please | JS/TS, conventional commits, monorepo with multiple packages | "Release PR" pattern, Google-maintained |
| Changesets | monorepo per-package versioning | explicit `.changeset/*.md` files |

The 2026 default for single-package JS/TS: release-please. For monorepos: Changesets or Changesets + release-please for orchestration.

## The release-please pattern

release-please creates a "Release PR" that bumps the version, updates the changelog, and prepares the release.

```
1. Merge feat: add option to skip validation
2. release-please opens a PR: "chore(main): release 1.4.0"
3. PR contains: version bump in package.json, CHANGELOG.md update
4. Merge the release PR → release-please tags v1.4.0 and publishes
```

The release PR is reviewable. The team can edit the changelog before merging. The actual release is atomic.

## The 0.x convention

For pre-1.0 versions (0.y.z), SemVer 2.0.0 says "anything may change at any time." The 2026 community convention is to treat 0.y.z as 0.MINOR.PATCH where 0.MINOR is the unstable public API and 0.PATCH is bug fixes.

The 1.0.0 release signals "this is the public API; breaking changes require a major bump."

## The deprecation discipline

A breaking change can be a minor version if the deprecated API has been documented as deprecated for at least one release cycle.

```typescript
/**
 * @deprecated since 1.3.0, will be removed in 2.0.0. Use `validate(input, { strict: true })` instead.
 */
export function validateStrict(input: string): boolean { ... }
```

The deprecation notice includes the version it was introduced and the version it will be removed in. Users have a release cycle to migrate.

## The 5 anti-patterns

1. **Breaking changes in minor versions.** The most common SemVer violation. The fix: automate version bumps from commit messages.
2. **No public API contract.** If everything is "public," nothing is. Document a stable surface; treat the rest as internal.
3. **Version drift across packages.** Monorepo packages should have aligned versions or per-package versions via Changesets.
4. **Pre-1.0 long-term.** If you're shipping 0.42.0, you've effectively committed to an API; either go 1.0 or document the instability.
5. **No changelog.** Automated changelog generation is one tool config away. No excuse.

## The API stability tiers

The 2026 convention is to mark API stability.

| Tier | Meaning | SemVer commitment |
|---|---|---|
| `@public` or `@stable` | guaranteed API | SemVer strictly |
| `@beta` | may change in minor | remove in minor; rename in major |
| `@alpha` or `@experimental` | may change at any time | no commitment |
| `@deprecated` | will be removed | removed in next major (typically) |

Document the tier in the docstring or type definition. The compiler / linter can enforce.

## The lockfile role

Lockfiles (package-lock.json, yarn.lock, pnpm-lock.yaml, poetry.lock, Pipfile.lock, Cargo.lock) pin exact versions for reproducible installs.

- **In libraries:** do not commit; consumers control the version
- **In applications:** commit; reproducible builds require it
- **In monorepos:** commit; workspaces depend on exact versions

The 2026 production pattern: lockfile committed for apps, not for libraries.

## Verification

The tell that SemVer is real:

- Conventional Commits are enforced via commitlint
- release-please or semantic-release runs on every push to main
- A "Release PR" is human-reviewed
- The public API is documented and tagged with stability tier
- Pre-1.0 versions are explicit about instability

The tell it isn't:

- Versions are bumped manually
- The changelog is hand-edited
- Breaking changes appear in minor versions
- No API stability tiers
- "We just use 1.0.0 forever"

## Gotchas

- **0.y.z is unstable.** Communicate this clearly; treat 0.MINOR as a "free to break" boundary.
- **Build metadata (+20130313144700) is ignored in precedence.** Useful for CI marks but doesn't bump the version.
- **Pre-release precedence is per-major.** 1.0.0-alpha < 1.0.0-beta < 1.0.0; 1.0.0-alpha.1 < 1.0.0-alpha.2.
- **License changes** are sometimes a major bump; some projects consider them patch. Document the policy.
- **Internal refactors are not breaking.** A refactor that doesn't change the public API is PATCH, not MAJOR. Even if the implementation is "completely different."

## Related

- `worktree/conventional-commits-2026.md` — commit message format
- `worktree/release-please-semantic-release.md` — release automation
- `worktree/conventional-commits-monorepo-changesets-2026.md` — monorepo versioning
- `worktree/branch-strategies-2026.md` — release branches

## Source URLs (verified 2026-08-10)

- https://semver.org/ — SemVer 2.0.0 specification
- https://www.conventionalcommits.org/ — Conventional Commits 1.0.0
- https://github.com/release-please/release-please
- https://github.com/semantic-release/semantic-release
- https://github.com/changesets/changesets
- https://keepachangelog.com/ — changelog format
- https://nodejs.org/api/documentation.html — Node.js stability tiers
- https://docs.npmjs.com/about-semantic-versioning — npm SemVer
