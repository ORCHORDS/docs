# Dependency Update Automation with Renovate

**Author:** example.com
**Project:** example project (example.com) — pnpm monorepo, Cloudflare Workers + Pages
**Last updated:** 2026-08-22

---

## Overview

Renovate is an open-source dependency update bot that automatically opens PRs when new versions of packages, GitHub Actions, Docker images, and other dependencies are released. For a pnpm monorepo targeting Cloudflare Workers, Renovate handles npm package updates, Wrangler version bumps, GitHub Actions version pinning, and mobile SDK updates — all with configurable grouping, scheduling, and automerge policies.

This article covers the full Renovate configuration for example project, explaining each decision so the team can maintain and extend it.

---

## Renovate vs Dependabot

Both tools open dependency update PRs automatically. Key differences for a pnpm monorepo:

| Capability | Renovate | Dependabot |
|-----------|---------|------------|
| pnpm lockfile update | Native support | Supported since 2023 |
| Grouped PRs (multiple packages in one PR) | Full control via `groupName` | Basic grouping only |
| Monorepo awareness | Yes — updates all workspace packages together | Limited |
| Custom versioning strategies | Yes (semver ranges, digest pinning, etc.) | Limited |
| Cloudflare Workers / Wrangler | First-class via npm | Via npm |
| GitHub Actions pinning to SHA | Yes | Yes |
| Automerge with conditions | Flexible | Basic |
| Self-hosted option | Yes (free) | GitHub-managed only |

**Recommendation:** Renovate for example project due to its superior monorepo grouping and automerge flexibility.

---

## Installation

The easiest path is the Renovate GitHub App:

1. Install from https://github.com/apps/renovate
2. Grant access to the example project repository.
3. Merge the onboarding PR Renovate opens (it creates `renovate.json5`).
4. Replace the generated config with the one below.

Alternatively, run Renovate as a GitHub Actions workflow (self-hosted, avoids sharing repository access with the app):

```yaml
# .github/workflows/renovate.yml
name: Renovate

on:
  schedule:
    - cron: "0 6 * * 1-5"   # weekdays at 06:00 UTC
  workflow_dispatch: {}       # allow manual trigger

jobs:
  renovate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: renovatebot/github-action@v40
        with:
          token: ${{ secrets.RENOVATE_TOKEN }}   # PAT with repo + workflow scopes
        env:
          LOG_LEVEL: info
```

---

## renovate.json5 — Complete Configuration

```json5
// renovate.json5
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": [
    "config:recommended",           // sensible defaults from Renovate
    ":dependencyDashboard",         // single issue tracking all pending updates
    ":semanticCommits",             // commit messages follow Conventional Commits
    ":separatePatchReleases",       // patch bumps get their own PR
    "group:allNonMajor",            // minor + patch go in one PR per group
  ],

  // ── Schedule ─────────────────────────────────────────────────────────────
  "schedule": ["before 7am on Monday"],   // one batch per week — avoids noise
  "timezone": "UTC",
  "prCreationHours": ["0-7"],

  // ── PR limits ────────────────────────────────────────────────────────────
  "prConcurrentLimit": 5,
  "prHourlyLimit": 2,

  // ── Commit message format (matches commitlint scope-enum) ─────────────
  "semanticCommitType": "chore",
  "semanticCommitScope": "deps",

  // ── pnpm monorepo ─────────────────────────────────────────────────────
  "pnpm": {
    "fileMatch": ["(^|/)pnpm-lock\\.yaml$"]
  },
  "enabledManagers": ["npm", "github-actions"],
  "packageRules": [

    // ── Group 1: Cloudflare ecosystem ──────────────────────────────────
    {
      "groupName": "Cloudflare Workers ecosystem",
      "matchPackageNames": [
        "wrangler",
        "@cloudflare/workers-types",
        "miniflare",
        "@cloudflare/vitest-pool-workers",
        "@cloudflare/d1",
        "hono",
      ],
      "automerge": false,       // always review Cloudflare updates
      "labels": ["dependencies", "cloudflare"],
      "reviewers": ["team:platform"],
    },

    // ── Group 2: GitHub Actions — pin to SHA ──────────────────────────
    {
      "groupName": "GitHub Actions",
      "matchManagers": ["github-actions"],
      "pinDigests": true,       // pin to commit SHA for supply-chain security
      "automerge": true,
      "automergeType": "pr",
      "automergeStrategy": "squash",
      "labels": ["dependencies", "ci"],
      // Only automerge patch/minor — major Actions changes need review
      "matchUpdateTypes": ["minor", "patch", "digest"],
    },

    // ── Group 3: Wrangler Action specifically ─────────────────────────
    {
      "groupName": "Wrangler GitHub Action",
      "matchPackageNames": ["cloudflare/wrangler-action"],
      "matchManagers": ["github-actions"],
      "automerge": false,       // wrangler deploy change = review required
      "labels": ["dependencies", "cloudflare", "ci"],
    },

    // ── Group 4: TypeScript + linting toolchain ───────────────────────
    {
      "groupName": "TypeScript and ESLint toolchain",
      "matchPackageNames": [
        "typescript",
        "@typescript-eslint/eslint-plugin",
        "@typescript-eslint/parser",
        "eslint",
        "eslint-config-prettier",
        "prettier",
      ],
      "automerge": false,
      "labels": ["dependencies", "toolchain"],
    },

    // ── Group 5: Mobile SDK updates (React Native + Expo) ─────────────
    {
      "groupName": "Mobile SDK — Expo and React Native",
      "matchPackageNames": [
        "expo",
        "expo-*",
        "react-native",
        "@react-native-*",
        "@react-navigation/*",
      ],
      "automerge": false,
      "labels": ["dependencies", "mobile"],
      "reviewers": ["team:mobile"],
      "schedule": ["before 7am on the first day of the month"],  // monthly cadence
      "stabilityDays": 7,       // wait 7 days after release before PR
      "minimumReleaseAge": "7 days",
    },

    // ── Group 6: Turborepo ────────────────────────────────────────────
    {
      "groupName": "Turborepo",
      "matchPackageNames": ["turbo", "turborepo"],
      "automerge": true,
      "automergeType": "pr",
      "labels": ["dependencies", "monorepo"],
    },

    // ── Group 7: Testing tools ────────────────────────────────────────
    {
      "groupName": "Testing — Vitest and related",
      "matchPackageNames": [
        "vitest",
        "@vitest/*",
        "happy-dom",
        "msw",
      ],
      "automerge": true,
      "automergeType": "pr",
      "labels": ["dependencies", "testing"],
    },

    // ── Automerge patch updates for non-critical deps ─────────────────
    {
      "description": "Automerge patch bumps for safe internal packages",
      "matchUpdateTypes": ["patch"],
      "matchPackageNames": [
        "zod",
        "date-fns",
        "clsx",
      ],
      "automerge": true,
      "automergeType": "pr",
    },

    // ── Never automerge major versions ─────────────────────────────────
    {
      "description": "Major updates always require manual review",
      "matchUpdateTypes": ["major"],
      "automerge": false,
      "labels": ["dependencies", "major-update"],
      "reviewers": ["team:platform"],
    },
  ],

  // ── Ignore specific packages ──────────────────────────────────────────
  "ignoreDeps": [
    "node",       // managed via .nvmrc / Volta — do not bump
  ],

  // ── Vulnerability alerts — immediate PRs ─────────────────────────────
  "vulnerabilityAlerts": {
    "labels": ["security", "priority:high"],
    "schedule": ["at any time"],  // override weekly schedule for CVEs
    "automerge": false,
  },

  // ── Dependency Dashboard ──────────────────────────────────────────────
  "dependencyDashboardTitle": "Dependency Updates Dashboard",
  "dependencyDashboardLabels": ["renovate"],

  // ── Commit and PR title format ────────────────────────────────────────
  "commitMessagePrefix": "chore(deps):",
  "prTitle": "chore(deps): {{{groupName}}} updates",
}
```

---

## Mobile SDK Update Strategy

Mobile SDK updates (React Native, Expo) deserve special treatment because:

1. **App stores require submission** — a native dependency bump may require a new binary build + store submission, not just a Workers re-deploy.
2. **Breaking changes are common** — Expo SDK major releases require coordinated migration across the native layer and JS code.
3. **Minimum app version gates** — once a new SDK is shipped, old app versions still call the API; the Workers API must handle both.

The configuration above schedules mobile SDK updates **monthly** with a **7-day stability wait**, giving the community time to find regressions before example project updates. The `team:mobile` reviewer ensures a native developer is always in the loop.

When an Expo SDK major PR opens:
1. Review the Expo SDK migration guide linked in the PR.
2. Run `pnpm expo upgrade` locally in `apps/mobile/`.
3. Build a development client and test on both iOS simulator and Android emulator.
4. Check whether any Workers API endpoints need version-gated changes (see the mobile feature gate article).
5. Submit the native build before merging the Renovate PR to `main`.

---

## Automerge Safety

Automerge is enabled only when all required CI checks pass. Ensure your branch protection requires:

- Lint
- Type-check
- Unit tests
- (for Workers packages) Wrangler type generation

Renovate waits for all status checks before automerging. If CI is red, the PR stays open.

---

## Viewing Pending Updates

Renovate creates a **Dependency Dashboard** issue in the repository. It lists:
- All open Renovate PRs
- Pending updates awaiting schedule
- Rate-limited updates
- Updates ignored via `ignoreDeps`

Open the issue and check boxes to trigger PRs out of schedule.

---

## Summary

- Renovate handles npm, GitHub Actions, and Wrangler updates across the entire pnpm monorepo.
- Cloudflare ecosystem packages and GitHub Actions are in named groups for clean PR history.
- Mobile SDK updates follow a monthly schedule with a stability buffer and mobile team review.
- Major updates always require manual review; patch updates for safe packages automerge.
- Vulnerability alerts bypass the weekly schedule and open immediately.

**References**
- Renovate documentation: https://docs.renovatebot.com
- Renovate GitHub App: https://github.com/apps/renovate
- `renovatebot/github-action`: https://github.com/renovatebot/github-action
