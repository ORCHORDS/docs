# changelog-generation

**Issue:** Maintaining a CHANGELOG.md file that is accurate, human-readable, and generated automatically
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hand-maintained changelogs drift out of sync with actual changes. Fully automated changelogs from raw commit history are too noisy. The solution is a structured commit convention plus a generator that filters and formats.

## Pattern / Solution
**Conventional Changelog toolchain**
```bash
# Install
npm install --save-dev conventional-changelog-cli

# Generate or update CHANGELOG.md
npx conventional-changelog -p angular -i CHANGELOG.md -s
```

**Keep-a-Changelog format (alternative — manual but structured)**
```markdown
# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [2.41.0] - 2026-08-11
### Added
- Apple Pay support in the checkout flow
- Dark mode toggle in user preferences

### Fixed
- Null pointer exception when refresh token is expired
- Incorrect price rounding for currencies with no decimal places

### Changed
- Search autocomplete now cached in Redis (50ms → 5ms p99)

[2.41.0]: https://github.com/org/repo/compare/v2.40.0...v2.41.0
```

**CI step: validate CHANGELOG updated on every feature PR**
```yaml
- name: Require CHANGELOG entry
  run: |
    if ! git diff --name-only origin/main | grep -q "CHANGELOG.md"; then
      echo "::error::Please add an entry to CHANGELOG.md for this PR."
      exit 1
    fi
```

**Release-it integration (all-in-one)**
```json
// .release-it.json
{
  "plugins": {
    "@release-it/conventional-changelog": {
      "preset": "angular",
      "infile": "CHANGELOG.md"
    }
  },
  "git": { "commitMessage": "chore(release): v${version}" },
  "github": { "release": true }
}
```

## Gotchas
- Do not mix auto-generated and hand-written changelog entries in the same file — pick one approach
- `[Unreleased]` section must be cleared on each release; automate this to avoid it accumulating stale entries
- Internal ticket references (JIRA-123) confuse external readers — strip or link them
- Changelogs in monorepos need package-scoped sections or separate files per package

## Related
- `release-notes-automation.md`
- `semver-best-practices.md`
- `artifact-versioning-strategy.md`
