# dependency-upgrade-strategies

**Issue:** Keep dependencies up to date without breaking
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your dependencies are 2 years out of date. A security
advisory lands. The fix is in a new version. You upgrade.
Half your code breaks. You spend 2 weeks fixing. The
upgrade was supposed to be a 1-hour task.

## Root cause
**Big-bang upgrades are painful.** A 2-year jump has 100+
breaking changes. Small, frequent upgrades are easier.

**Source:** Dependabot docs:
https://docs.github.com/en/code-security/dependabot

## The "small, frequent upgrades" rule

Upgrade often (weekly or monthly). Each upgrade is small
(1-2 packages). A small upgrade is easy to review, test,
and ship.

```
❌ Bad: 1 upgrade per year (huge jump)
✅ Good: 1 upgrade per week (small jump)
```

## The "semver" understanding

Semantic Versioning (semver): `MAJOR.MINOR.PATCH`
- **MAJOR:** Breaking changes
- **MINOR:** New features (backward compatible)
- **PATCH:** Bug fixes (backward compatible)

```json
{
  "dependencies": {
    "lodash": "^4.17.21",  // ^4.x.x — allows MINOR + PATCH
    "react": "18.2.0",     // exact — no upgrades
  }
}
```

The `^` prefix allows MINOR + PATCH upgrades. The `~`
prefix allows PATCH only.

## The "lockfile" pattern

Use a lockfile (`package-lock.json`, `pnpm-lock.yaml`):
- Locks the exact versions
- Ensures everyone has the same deps
- Required for reproducible builds

```bash
# Commit the lockfile
git add package-lock.json

# Use the lockfile in CI
npm ci  # Installs from lockfile, not package.json
```

`npm ci` is faster + more reliable than `npm install` in
CI.

## The "Dependabot" pattern

Use Dependabot for automated PRs:
```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    groups:
      patch-and-minor:
        update-types: ["minor", "patch"]
```

Dependabot opens a PR every week for outdated deps. The
team reviews + merges.

## The "Renovate" alternative

Renovate is similar to Dependabot but more configurable:
- More flexible grouping
- Auto-merge for patches
- More ecosystems

```json
{
  "extends": ["config:base"],
  "packageRules": [
    {
      "matchUpdateTypes": ["minor", "patch"],
      "groupName": "all non-major",
      "automerge": true
    }
  ]
}
```

## The "auto-merge" pattern

For patch updates (bug fixes, no breaking changes), auto-
merge:
```yaml
# GitHub: Settings → Allow auto-merge
# Renovate/Dependabot: open the PR; CI green → auto-merge
```

A patch upgrade that passes CI is safe to ship.

For minor upgrades, auto-merge is risky (new features,
deprecations). Require manual review.

## The "breaking change upgrade" pattern

For major upgrades (e.g. React 17 → 18), the steps:
1. **Read the migration guide**
2. **Update the package**
3. **Fix the deprecations + errors**
4. **Test thoroughly**
5. **Deploy to staging**
6. **Monitor**
7. **Deploy to production**

For a large project, a major upgrade is a project (not a
PR). Plan accordingly.

## The "peer dependency" gotcha

```bash
npm install foo
# npm warn peer dep @types/react@^17 not satisfied by @types/react@^18
```

A peer dep is a "I need this version" hint. If the
installed version doesn't match, you may have issues at
runtime.

Fix:
1. **Update the dep** to a compatible version
2. **Install the peer dep** explicitly
3. **Use a peer dep manager** (e.g. `npx install-peerdeps`)

## The "transitive dependency" gotcha

You depend on `A`. `A` depends on `B`. You don't directly
depend on `B`. But `A` upgraded `B` and it broke.

Fix:
1. **Pin `B` to a working version** (overrides)
2. **Update `A`** to a version that uses a working `B`
3. **Replace `A`** with an alternative

```json
{
  "overrides": {
    "B": "1.2.3"
  }
}
```

## The "vulnerability" pattern

For security vulnerabilities, prioritize by severity:
- **Critical:** Fix within 24h
- **High:** Fix within 7 days
- **Medium:** Fix within 30 days
- **Low:** Fix in the next regular cycle

```bash
# npm audit
npm audit
# Shows vulnerabilities + recommended fixes

# Auto-fix where possible
npm audit fix
# Updates to non-breaking versions
```

For breaking updates needed for security, accept the
breakage.

## The "deprecated" pattern

For deprecated packages:
1. **Find the replacement** (usually in the deprecation
   notice)
2. **Plan the migration** (code changes, tests)
3. **Migrate** (small PR per file)
4. **Remove the old dep**

Don't keep using deprecated packages "because they still
work." They may stop working at any time.

## The "dependency review" pattern

In CI, review deps:
```yaml
# GitHub Action: dependency-review-action
- uses: actions/dependency-review-action@v1
  with:
    fail-on-severity: high
```

A PR that adds a new dep is reviewed for:
- License (MIT, Apache, etc. — not GPL unless compatible)
- Maintenance (active project, not abandoned)
- Security (no known vulnerabilities)
- Size (bundle size impact)

## The "monorepo" pattern

For monorepos, use workspace tools:
```json
{
  "workspaces": ["packages/*"]
}
```

```bash
# Update a specific package
npm update lodash --workspace=packages/api

# Update all
npm update --workspaces
```

## Verification
- **Test:** CI runs `npm audit` + `npm test` on every dep PR
- **Live:** Dependabot runs weekly
- **Audit:** Quarterly review of dependencies

## Gotchas
- **The "big-bang upgrade" anti-pattern.** A 2-year jump is
  a project; a 1-month jump is a PR.
- **The "auto-merge everything" anti-pattern.** Major
  upgrades need human review.
- **The "ignore deprecations" anti-pattern.** Deprecations
  become removals. Plan ahead.
- **The "npm install in CI" anti-pattern.** Use `npm ci`
  for reproducibility.
- **The "transitive dep version" anti-pattern.** The
  top-level version is not the only version; use `npm
  ls` to see the full tree.
- **The "no lockfile" anti-pattern.** A missing lockfile
  means non-reproducible builds.

## Related
- `github/dependabot-config.md`
- `infra/pnpm-workspaces-monorepo.md`
- `safe-deploy-checklist.md`
- `pr-template-and-issue-templates.md`
- Dependabot: https://docs.github.com/en/code-security/dependabot
- Renovate: https://docs.renovatebot.com/
- npm audit: https://docs.npmjs.com/cli/v10/commands/npm-audit
