# feature-cookbook-changelog

**Issue:** Changelog — release notes, breaking changes
**Date:** 2026-08-09
**Status:** documented

## Symptom
You release a new version. Users ask "what changed?"
You have no idea. You dig through git log. You
write a quick summary. The user is still confused.

## Root cause
**Without a changelog, releases are opaque.** Write one.

**Source:** Keep a Changelog:
https://keepachangelog.com/

## The "changelog" concept

A changelog is a curated, chronologically ordered
list of notable changes for each version of a project.

**Source:** Keep a Changelog:
https://keepachangelog.com/

## The "changelog format" pattern

For a changelog:
```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.0.0] - 2026-08-09

### Added
- New `preferences` field on User
- New `getUserProfile` endpoint
- Support for the `X-Region` header

### Changed
- **BREAKING:** User.email is now required
- **BREAKING:** Removed legacy `getUser` endpoint
- Improved login performance (10x faster)

### Deprecated
- The `displayName` field is deprecated; use `fullName`

### Removed
- **BREAKING:** Removed `getUserById` endpoint; use
  `getUser(id)` instead

### Fixed
- Login was failing for users with old passwords (#123)
- The `signup` endpoint was returning 500 for valid input (#456)

### Security
- Updated `axios` to patch a vulnerability

## [1.4.2] - 2026-07-20

### Fixed
- Login was failing for users with old passwords
```

The changelog is curated.

## The "changelog categories" pattern

For categories:
- **Added:** New features
- **Changed:** Changes in existing functionality
- **Deprecated:** Soon-to-be removed features
- **Removed:** Removed features
- **Fixed:** Bug fixes
- **Security:** Security fixes

The categories are clear.

## The "breaking change" pattern

For breaking changes, mark explicitly:
```markdown
### Changed
- **BREAKING:** User.email is now required
```

The breaking change is obvious.

## The "PR to changelog" pattern

For PRs that update the changelog:
1. **PR template:** "Add a changelog entry"
2. **CI:** Check the changelog is updated
3. **Reviewer:** Verify the entry

The changelog is part of the PR.

## The "release process" pattern

For a release:
1. **Bump version:** In `package.json`
2. **Move Unreleased to versioned:** In CHANGELOG.md
3. **Tag:** `git tag v2.0.0`
4. **Build:** `npm run build`
5. **Publish:** To npm / GitHub
6. **Announce:** Blog post, email, social

The release is structured.

## The "changelog tooling" pattern

For tooling:
- **standard-version:** Automates the process
- **release-please:** Google + GitHub's tool
- **lerna:** Monorepo versioning
- **changesets:** Monorepo versioning

```bash
# standard-version
npx standard-version

# release-please
# Uses PR labels + GitHub Actions
```

The tooling is automated.

## The "automated changelog" pattern

For automation:
```yaml
# GitHub Actions
- name: Bump version
  uses: cycjimmy/semantic-release-action@v4
  with:
    semantic_version: 22
- name: Create release
  uses: ncipollo/release-action@v1
```

The changelog is auto-generated from PRs.

## The "release notes" pattern

For release notes (for users):
- **Headline:** What's the big change?
- **Highlights:** 2-3 main features
- **Breaking changes:** What users need to do
- **Bug fixes:** Notable fixes
- **Migration guide:** How to upgrade

```markdown
# v2.0: Faster, simpler, more secure

## Highlights
- 10x faster login
- New preferences API
- Security hardening

## Breaking changes
- `User.email` is now required — see migration guide
- `getUserById` removed — use `getUser(id)`

## Migration
1. Update `User.email` to required
2. Replace `getUserById(id)` with `getUser(id)`

## Bug fixes
- Login was failing for users with old passwords
```

The release notes are user-friendly.

## The "changelog anti-pattern" anti-patterns

### 1. No changelog
- **Issue:** Users don't know what changed
- **Fix:** Write a changelog

### 2. Auto-generated from git
- **Issue:** Noisy, not curated
- **Fix:** Curated, human-written

### 3. "Misc changes"
- **Issue:** Vague
- **Fix:** Specific categories

### 4. No version
- **Issue:** No way to know
- **Fix:** Version + date

### 5. No breaking change flag
- **Issue:** Users surprised
- **Fix:** **BREAKING:** marker

### 6. No migration guide
- **Issue:** Users can't upgrade
- **Fix:** Provide a guide

## Verification
- **Test:** Changelog is updated on each PR
- **Test:** Release notes are clear
- **Live:** Changelog is published
- **Audit:** Quarterly release review

## Gotchas
- **The "no changelog" anti-pattern.** Write one.
- **The "auto-generated" anti-pattern.** Curate it.
- **The "no breaking flag" anti-pattern.** Mark
  explicitly.

## Related
- `feature-cookbook-versioning.md`
- `api-versioning.md`
- `feature-cookbook-feature-lifecycle.md`
- `feature-cookbook-rfc-process.md`
- Keep a Changelog: https://keepachangelog.com/
- SemVer: https://semver.org/
- standard-version: https://github.com/conventional-changelog/standard-version
- release-please: https://github.com/googleapis/release-please
