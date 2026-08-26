# conventional-commits

**Issue:** Conventional Commits + changelog
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your git log is "fixed bug", "WIP", "more stuff".
You can't auto-bump version. Changelog is manual.
You wish you had structure.

## Root cause
**Unstructured commits = no automation.** Use
Conventional Commits.

**Source:** Conventional Commits 1.0.0 + ReleasePad.

## The "Conventional Commits" concept

For commits:
```
<type>(<optional scope>): <description>
<optional body>
<optional footer>
```

The format is parseable.

## The "types" pattern

For types:
- **feat:** New feature (MINOR)
- **fix:** Bug fix (PATCH)
- **docs:** Docs only
- **style:** Formatting (no code)
- **refactor:** Code change (not feat/fix)
- **perf:** Performance
- **test:** Tests
- **build:** Build/deps
- **ci:** CI config
- **chore:** Other (not source/test)
- **revert:** Undo

The types are fixed.

## The "scope" pattern

For scope:
- **Optional:** Parens
- **Noun:** Section of codebase
- **Examples:** `feat(api)`, `fix(auth)`, `refactor(db)`
- **Convention:** Per team

The scope is contextual.

## The "BREAKING CHANGE" pattern

For breaking:
- **Footer:** `BREAKING CHANGE: description`
- **Or:** `!` after type
- **Examples:**
  - `feat(api)!: redesign endpoints`
  - `fix!: drop legacy support`
- **SemVer:** MAJOR

The breaking is marked.

## The "feat" pattern

For feat:
- **SemVer:** MINOR bump
- **Changelog:** Features section
- **Examples:** `feat: add OAuth2 login`
- **With scope:** `feat(api): add /v2/users`

The feat is feature.

## The "fix" pattern

For fix:
- **SemVer:** PATCH bump
- **Changelog:** Bug Fixes section
- **Examples:** `fix: null check in payment flow`
- **With scope:** `fix(auth): token expiry race`

The fix is bug.

## The "chore" pattern

For chore:
- **SemVer:** No bump
- **Changelog:** Hidden (or "Other")
- **Use:** Deps, configs, tooling
- **Examples:** `chore: bump dep`

The chore is meta.

## The "revert" pattern

For revert:
- **Format:** `revert: <message>`
- **Footer:** `This reverts commit <sha>.`
- **Why:** Traceable

The revert is structured.

## The "commitlint" pattern

For enforcement:
```bash
# Install
npm install --save-dev @commitlint/cli @commitlint/config-conventional

# config
echo "module.exports = {extends: ['@commitlint/config-conventional']}" > commitlint.config.js

# Husky hook
npx husky add .husky/commit-msg 'npx --no -- commitlint --edit ${1}'
```

The lint enforces.

## The "semantic-release" pattern

For automation:
- **Reads:** Commit history
- **Bumps:** SemVer automatically
- **Generates:** Changelog
- **Publishes:** To npm
- **Tag:** Git tag

The release is automatic.

## The "standard-version" pattern

For manual control:
- **Reads:** Commits
- **Bumps:** Per config
- **Changelog:** Generated
- **No auto-publish:** Manual tag

The version is controlled.

## The "keep a changelog" pattern

For changelog:
- **File:** `CHANGELOG.md`
- **Format:** keepachangelog.com
- **Order:** Reverse chronological
- **Categories:** Added, Changed, Deprecated,
  Removed, Fixed, Security

The changelog is standard.

## The "6 changelog categories" pattern

For categories:
- **Added:** New features
- **Changed:** Modified functionality
- **Deprecated:** Phasing out
- **Removed:** Permanently removed
- **Fixed:** Bug fixes
- **Security:** Vuln patches

The 6 are the structure.

## The "changelog vs release notes" pattern

For difference:
- **Changelog:** Cumulative, all changes
- **Release notes:** Per version, formal
- **Often:** Used interchangeably
- **Practice:** Changelog for devs, release notes for users

The distinction is per audience.

## The "for humans" pattern

For audience:
- **User-facing:** Plain language
- **Dev-facing:** Technical
- **Tone:** Active voice
- **Format:** Bullet list
- **Link:** To docs

The changelog is for humans.

## The "release schedule" pattern

For cadence:
- **Weekly:** SaaS
- **Monthly:** Enterprise
- **Per deploy:** Continuous
- **Major:** Quarterly

The cadence is per product.

## The "no CTA" anti-pattern

For changelog:
- **Issue:** No engagement
- **Fix:** Call-to-action (feedback button)

The CTA is required.

## The "not accessible" anti-pattern

For hidden:
- **Issue:** Users don't find
- **Fix:** Link in nav + widget

The changelog is visible.

## The "no version" anti-pattern

For no version:
- **Issue:** Can't track change
- **Fix:** SemVer

The version is required.

## The "junk commits" anti-pattern

For junk:
- **Issue:** "WIP", "fix typo"
- **Fix:** commitlint

The lint is enforced.

## The "no automation" anti-pattern

For manual:
- **Issue:** Changelog is 2 hours
- **Fix:** semantic-release

The automation is required.

## The "grandfather" pattern

For adoption:
- **Old history:** Don't rewrite
- **Start date:** Today
- **Old commits:** Unstructured (ignored)
- **New commits:** Structured

The grandfather is pragmatic.

## The "cheat sheet" pattern

For team:
- **Put:** In CONTRIBUTING.md
- **Hold:** 15-min team discussion
- **Agree:** Scope names
- **Tooling:** Enforces

The cheat sheet is shared.

## The "PR title" pattern

For PR:
- **Use:** Same format
- **Squash:** Conventional title
- **Result:** Clean main history

The PR is conventional.

## The "commit message body" pattern

For body:
- **When:** Detailed explanation
- **Why:** Context
- **Refs:** Issue, PR
- **Co-author:** Multiple

The body is rich.

## The "conventional commits checklist" pattern

For checklist:
- [ ] commitlint configured
- [ ] Husky hook installed
- [ ] Cheat sheet in CONTRIBUTING
- [ ] Types: feat, fix, chore, etc.
- [ ] Scope: per team
- [ ] BREAKING CHANGE: footer or !
- [ ] semantic-release or standard-version
- [ ] CHANGELOG.md auto-generated
- [ ] Old history grandfathered
- [ ] PR title conventional

The checklist is 10.

## Verification
- **Test:** Commits parsed
- **Test:** Version auto-bumped
- **Test:** Changelog generated
- **Test:** Breaking change detected
- **Audit:** Quarterly

## Gotchas
- **The "junk commits" anti-pattern.** Lint.
- **The "no automation" anti-pattern.** semantic-release.
- **The "no version" anti-pattern.** SemVer.

## Related
- `worktree/squash-merge-default.md`
- `worktree/cherry-pick-revert-bisect.md`
- `github/issue-and-pr-templates.md`
- `patterns/documentation.md`
- Conventional Commits: https://www.conventionalcommits.org/
- ReleasePad: https://www.releasepad.io/blog/conventional-commits-developers-guide-to-better-changelogs/
- AnnounceKit: https://announcekit.app/blog/keep-a-changelog/
