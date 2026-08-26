# dependency-management-2026

**Issue:** A team's package.json has 2000 dependencies, 50 of them outdated. The team debates npm-check-updates, Renovate, Dependabot, in-house scripts. The team needs the 2026 reference for dependency management.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 4 management strategies

1. **Manual.** Run `npm outdated` quarterly. Tedious, drifts.
2. **ncu (npm-check-updates).** CLI tool, manual trigger.
3. **Dependabot.** GitHub-native, PR-based, config in `.github/dependabot.yml`.
4. **Renovate.** Bot, very configurable, self-hosted option.

## The 5-step Dependabot config

1. **Schedule.** Weekly cron, off-hours.
2. **Group updates** (e.g., all `eslint-*` in one PR).
3. **Limit open PRs** (default 5; raise to 10 for fast-moving).
4. **Auto-merge** patch and minor updates after CI passes.
5. **Ignore major versions** until manually approved.

## The 5 best practices

1. **Pin exact versions** in production, range in development.
2. **Lockfile** committed (package-lock.json, yarn.lock, pnpm-lock.yaml).
3. **Lockfile verified in CI** (`npm ci` not `npm install`).
4. **Group related updates** (Renovate's `groupName` or Dependabot's `groups`).
5. **Auto-merge safe updates** (patch, dev-deps) after CI.

## The 5 anti-patterns

1. **Floating versions** (`"react": "^18"` with `npm install` in CI) - non-reproducible.
2. **No lockfile** in repo.
3. **Dependabot config** that opens 50 PRs per day.
4. **Auto-merge major versions** breaking production.
5. **Ignoring security updates** to avoid churn.

## Gotchas

- Dependabot free for public repos; private repos need GitHub Advanced Security or free for some.
- Renovate is self-hostable for free.
- `npm ci` requires package-lock.json; `npm install` can modify it.
- Some packages have peer-dependency conflicts that block major upgrades.
- npm provenance requires GitHub Actions OIDC for `--provenance` flag.

## Source URLs (verified 2026-08-10)

- https://docs.github.com/en/code-security/dependabot
- https://docs.renovatebot.com/
- https://github.com/raineorshine/npm-check-updates
- https://docs.npmjs.com/cli/v10/commands/npm-ci
