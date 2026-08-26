# semver-best-practices

**Issue:** SemVer — versioning + pre-1.0
**Date:** 2026-08-09
**Status:** documented

## Symptom
You bump version by hand. Some apps break. The
changelog is wrong. You wish you had SemVer.

## Root cause
**Manual version = bugs.** Use SemVer.

**Source:** semver.org + semver 2.0.

## The "SemVer" concept

Semantic Versioning:
- **MAJOR.MINOR.PATCH**
- **MAJOR:** Breaking
- **MINOR:** Feature (backward compat)
- **PATCH:** Bug fix

The version is meaningful.

## The "MAJOR" pattern

For major:
- **When:** Breaking API change
- **Reset:** MINOR + PATCH to 0
- **Example:** 1.5.3 → 2.0.0
- **Impact:** Users must update

The major is breaking.

## The "MINOR" pattern

For minor:
- **When:** Backward-compat feature
- **Reset:** PATCH to 0
- **Example:** 1.5.3 → 1.6.0
- **Impact:** Optional upgrade

The minor is feature.

## The "PATCH" pattern

For patch:
- **When:** Bug fix (compat)
- **Reset:** Nothing
- **Example:** 1.5.3 → 1.5.4
- **Impact:** Safe upgrade

The patch is fix.

## The "0.y.z" pattern

For pre-1.0:
- **Anything may change**
- **API not stable**
- **Use:** Initial dev
- **Bump:** 0.1.0 → 0.2.0 → 1.0.0

The 0.y.z is unstable.

## The "when 1.0.0" pattern

For 1.0.0:
- **In production:** Yes
- **Stable API:** Yes
- **Users depend:** Yes
- **Worry about compat:** No

The 1.0.0 is committed.

## The "pre-release" pattern

For pre-release:
- **Format:** `-alpha.1`, `-beta.2`, `-rc.1`
- **Order:** < normal
- **Example:** `2.0.0-rc.1` < `2.0.0`
- **Use:** Beta, RC, alpha

The pre-release is below.

## The "build metadata" pattern

For build:
- **Format:** `+20210101`
- **Ignored:** In version comparison
- **Use:** Build ID, hash
- **Example:** `1.0.0+sha.abc`

The build is meta.

## The "deprecation" pattern

For deprecate:
- **Add:** In MINOR
- **Document:** In release
- **Remove:** In next MAJOR
- **Min:** One MINOR with deprecate

The deprecate is staged.

## The "API public" pattern

For public API:
- **Declare:** First
- **Document:** Reference
- **Stability:** Once 1.0.0
- **Change:** Only with MAJOR

The API is declared.

## The "1.0.0 rule" pattern

For 1.0.0:
- **Production:** Already
- **Stable:** Yes
- **Bumping major:** Forces thought
- **Cost/benefit:** Evaluated

The major is thought.

## The "breaking change" pattern

For breaking:
- **Avoid:** If possible
- **Add:** API alongside
- **Deprecate:** First
- **Remove:** In next major

The breaking is graceful.

## The "dep + SemVer" pattern

For deps:
- **Your deps:** Their SemVer
- **Conflict:** Possible
- **Bump major:** Per breaking
- **Lock file:** Pin exact

The deps are managed.

## The "lock file" pattern

For lock:
- **package-lock.json:** Pinned
- **go.sum:** Hashed
- **Pipfile.lock:** Pinned
- **CI:** --frozen-lockfile

The lock is required.

## The "no SemVer" anti-pattern

For no SemVer:
- **Issue:** Version meaningless
- **Fix:** Adopt SemVer

The version is SemVer.

## The "floating versions" anti-pattern

For floats:
- **Issue:** Surprise updates
- **Fix:** Exact in lock

The version is pinned.

## The "major without thought" anti-pattern

For major bump:
- **Issue:** Easy to bump
- **Fix:** Cost/benefit review

The major is reviewed.

## The "deprecate + remove same release" anti-pattern

For deprecate:
- **Issue:** No warning
- **Fix:** Deprecate in MINOR

The deprecate is staged.

## The "modify released version" anti-pattern

For modify:
- **Issue:** Tamper
- **Fix:** New version

The version is immutable.

## The "0.y.z in production" anti-pattern

For 0.y.z:
- **Issue:** Unstable
- **Fix:** Bump to 1.0.0

The 1.0.0 is committed.

## The "versioning automation" pattern

For automation:
- **semantic-release:** Auto from commits
- **standard-version:** Manual control
- **Changesets:** PRs declare
- **release-please:** Google's tool

The automation is per need.

## The "semantic-release" pattern

For auto:
- **Reads:** Commits
- **Bumps:** Per conventional
- **Changelog:** Generated
- **Tag:** Git
- **Publish:** npm

The release is auto.

## The "changesets" pattern

For PRs:
- **PR:** Declares changeset
- **Bot:** Bumps on merge
- **Versions:** Independent
- **Use:** Monorepo

The changesets is per PR.

## The "release-please" pattern

For Google's:
- **Conventional:** Commits
- **Auto:** PR with changelog
- **Merge:** Releases

The release is per PR.

## The "tool choice" pattern

For choice:
| Tool | Use |
|---|---|
| semantic-release | Auto from commits |
| standard-version | Manual control |
| Changesets | Monorepo, per PR |
| release-please | Google's conventional |
| Nx release | Nx monorepo |

The choice is per need.

## The "versioning policy" pattern

For policy:
- **0.y.z:** Until stable
- **1.0.0+:** Strict
- **Pre-release:** Per branch
- **Tag:** Annotated

The policy is documented.

## The "API change" pattern

For change:
- **Add:** Backward compat → MINOR
- **Change:** Backward compat → PATCH
- **Remove:** Backward incompat → MAJOR
- **Rename:** MAJOR (or deprecate + new)

The change is per impact.

## The "consumer" pattern

For consumer:
- **^1.2.3:** Compatible (1.x.y)
- **~1.2.3:** Patch only (1.2.x)
- **1.2.3:** Exact
- **>=1.2.3 <2.0.0:** Range

The range is per need.

## The "caret vs tilde" pattern

For range:
- **^1.2.3:** MINOR + PATCH
- **~1.2.3:** PATCH only
- **Use:** ^ for most, ~ for strict

The range is per use.

## The "SemVer checklist" pattern

For checklist:
- [ ] Public API declared
- [ ] 0.y.z → 1.0.0 when stable
- [ ] MAJOR for breaking
- [ ] MINOR for feature
- [ ] PATCH for fix
- [ ] Deprecate before remove
- [ ] Pre-release for beta
- [ ] Lock file committed
- [ ] Changelog generated
- [ ] Automated (semantic-release etc.)
- [ ] Annotated tags

The checklist is 11.

## Verification
- **Test:** Version bumps correctly
- **Test:** Changelog generated
- **Test:** Deps install
- **Test:** No surprises
- **Audit:** Quarterly

## Gotchas
- **The "no SemVer" anti-pattern.** Adopt.
- **The "floating versions" anti-pattern.** Pin.
- **The "deprecate + remove same" anti-pattern.** Stage.

## Related
- `worktree/conventional-commits.md`
- `worktree/squash-merge-default.md`
- `infra/monorepo-2026.md`
- `patterns/feature-flags-best-practices.md`
- `patterns/api-versioning.md`
- SemVer: https://semver.org/
- SemVer 2.0: https://www.semver.org/
- FAQ: https://semver-versioning.org/faq/
