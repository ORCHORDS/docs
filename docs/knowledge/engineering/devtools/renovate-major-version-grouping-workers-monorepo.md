# Renovate Major Version Grouping for Workers Monorepo

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your Cloudflare Workers monorepo receives 40+ Renovate PRs per week. Minor and patch bumps are noise; major bumps (`wrangler` 3→4, `hono` 3→4, `@cloudflare/workers-types` 3→4) arrive unannounced and sometimes break builds silently. You want: (1) major bumps grouped by ecosystem into a single reviewable PR, (2) minor/patch updates auto-merged after CI, and (3) Workers-specific packages treated with extra caution.

---

## Context

Renovate's `packageRules` array is evaluated top-to-bottom, with later rules overriding earlier ones for matched packages. The strategy here:

- **Group all Workers-ecosystem majors** into a weekly PR that a human must approve.
- **Auto-merge** minor/patch bumps for low-risk packages after CI passes.
- **Pin** `wrangler` and `@cloudflare/workers-types` to exact versions in a separate lockstep group so they always upgrade together.
- **Schedule** major PRs on Monday mornings to avoid Friday surprises.

Stack:

- `renovate` ^38 (GitHub App or self-hosted)
- `pnpm` workspaces monorepo
- Cloudflare Workers, Wrangler, Miniflare, Hono

---

## Base Renovate Config

`renovate.json` at the repository root:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": [
    "config:recommended",
    ":dependencyDashboard",
    ":separateMajorReleases",
    ":prConcurrentLimit10"
  ],
  "timezone": "Europe/London",
  "schedule": ["after 9am and before 5pm on weekdays"],
  "labels": ["dependencies"],
  "prCreation": "immediate",
  "platformAutomerge": true,
  "automergeStrategy": "squash"
}
```

---

## Grouping Workers-Ecosystem Majors

```json
{
  "packageRules": [
    {
      "description": "Group all Cloudflare Workers ecosystem major upgrades",
      "matchPackageNames": [
        "wrangler",
        "miniflare",
        "@cloudflare/workers-types",
        "@cloudflare/vitest-pool-workers",
        "@cloudflare/pages-shared",
        "@cloudflare/kv-asset-handler",
        "@cloudflare/workers-oauth-provider"
      ],
      "matchUpdateTypes": ["major"],
      "groupName": "Cloudflare Workers ecosystem (major)",
      "groupSlug": "cloudflare-workers-major",
      "schedule": ["on monday before 10am"],
      "automerge": false,
      "labels": ["dependencies", "breaking-change", "cloudflare"]
    }
  ]
}
```

The `schedule` here overrides the global schedule so major Cloudflare PRs land Monday morning when engineers are ready to triage.

---

## Lockstep Group for wrangler + workers-types

`wrangler` and `@cloudflare/workers-types` must match major versions — mismatches cause TypeScript errors on `env` binding types:

```json
{
  "packageRules": [
    {
      "description": "Keep wrangler and workers-types on the same major version",
      "matchPackageNames": [
        "wrangler",
        "@cloudflare/workers-types"
      ],
      "groupName": "Wrangler + workers-types lockstep",
      "groupSlug": "wrangler-types-lockstep",
      "automerge": false,
      "commitMessageExtra": "(lockstep {{newVersion}})"
    }
  ]
}
```

Because `packageRules` are additive, this rule also applies on top of the major grouping rule; the lockstep group name wins for non-major updates.

---

## Auto-merge Minor and Patch for Low-risk Packages

```json
{
  "packageRules": [
    {
      "description": "Auto-merge minor and patch for dev tooling",
      "matchPackageNames": [
        "typescript",
        "vitest",
        "@vitest/coverage-v8",
        "prettier",
        "eslint",
        "@typescript-eslint/parser",
        "@typescript-eslint/eslint-plugin",
        "lefthook",
        "knip"
      ],
      "matchUpdateTypes": ["minor", "patch"],
      "automerge": true,
      "automergeType": "pr",
      "platformAutomerge": true,
      "minimumReleaseAge": "3 days"
    },
    {
      "description": "Auto-merge patch-only for all other packages",
      "matchUpdateTypes": ["patch"],
      "automerge": true,
      "automergeType": "pr",
      "platformAutomerge": true,
      "minimumReleaseAge": "5 days",
      "excludePackageNames": [
        "wrangler",
        "@cloudflare/workers-types",
        "miniflare"
      ]
    }
  ]
}
```

`minimumReleaseAge` prevents same-day auto-merge, which catches supply-chain attacks that appear briefly on npm before being taken down.

---

## Grouping All Non-major Bumps Into One PR

For teams that prefer a single weekly "dependencies" PR rather than per-package PRs:

```json
{
  "packageRules": [
    {
      "description": "Batch all non-major, non-Cloudflare updates into a weekly PR",
      "matchUpdateTypes": ["minor", "patch"],
      "excludePackageNames": [
        "wrangler",
        "@cloudflare/workers-types",
        "miniflare",
        "@cloudflare/vitest-pool-workers"
      ],
      "groupName": "All non-major dependencies",
      "groupSlug": "all-non-major",
      "schedule": ["on friday before 12pm"],
      "automerge": true,
      "automergeType": "pr",
      "platformAutomerge": true
    }
  ]
}
```

---

## Complete renovate.json Example

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": [
    "config:recommended",
    ":dependencyDashboard",
    ":separateMajorReleases",
    ":prConcurrentLimit10"
  ],
  "timezone": "Europe/London",
  "schedule": ["after 9am and before 5pm on weekdays"],
  "labels": ["dependencies"],
  "prCreation": "immediate",
  "platformAutomerge": true,
  "automergeStrategy": "squash",
  "packageRules": [
    {
      "matchPackageNames": [
        "wrangler",
        "@cloudflare/workers-types",
        "miniflare",
        "@cloudflare/vitest-pool-workers"
      ],
      "matchUpdateTypes": ["major"],
      "groupName": "Cloudflare Workers ecosystem (major)",
      "groupSlug": "cloudflare-workers-major",
      "schedule": ["on monday before 10am"],
      "automerge": false,
      "labels": ["dependencies", "breaking-change", "cloudflare"]
    },
    {
      "matchPackageNames": ["wrangler", "@cloudflare/workers-types"],
      "groupName": "Wrangler + workers-types lockstep",
      "groupSlug": "wrangler-types-lockstep",
      "automerge": false
    },
    {
      "matchUpdateTypes": ["minor", "patch"],
      "excludePackageNames": [
        "wrangler",
        "@cloudflare/workers-types",
        "miniflare"
      ],
      "groupName": "All non-major dependencies",
      "groupSlug": "all-non-major",
      "schedule": ["on friday before 12pm"],
      "automerge": true,
      "automergeType": "pr",
      "platformAutomerge": true,
      "minimumReleaseAge": "3 days"
    }
  ]
}
```

---

## Anti-patterns

- **No `minimumReleaseAge`**: Auto-merging on the same day a package is published is the highest-risk window for supply-chain attacks. Always add at least 3 days for auto-merged packages.
- **Grouping majors across ecosystems**: A single "all majors" group mixes breaking changes from unrelated packages. Reviewers cannot reason about a PR that bumps `wrangler`, `react`, and `postgres` simultaneously.
- **Setting `automerge: true` on `wrangler` major**: Wrangler major bumps change `wrangler.toml` schema, binding APIs, and the Miniflare version — these always require manual review and a build test.
- **Using `matchPackagePrefixes` for `@cloudflare/*` broadly**: It catches packages that are not Workers-related (`@cloudflare/zod`, `@cloudflare/vitest-pool-workers` config) and may suppress auto-merge for things that are safe.
- **Not using `groupSlug`**: Without `groupSlug`, Renovate derives the branch name from `groupName`, which changes if you rename the group, orphaning open PRs.

---

## Gotchas

- `packageRules` are applied in array order; later rules **override** earlier ones for the same field. Put broad catch-all rules first, specific package rules last.
- `platformAutomerge` relies on GitHub branch protection allowing the Renovate app to bypass required reviews. If your repository has a required reviewer rule, `platformAutomerge` silently falls back to Renovate API-merge.
- The Dependency Dashboard issue (enabled by `:dependencyDashboard`) lets you manually trigger a specific group's PR on demand. Use it to force a Monday major PR mid-week if a critical CVE drops.
- pnpm workspaces: Renovate discovers packages in `pnpm-workspace.yaml` automatically. Packages shared via `pnpm catalog:` are updated in `pnpm-workspace.yaml` directly; ensure your `fileFilters` (or the default) includes that file.
- `schedule` is evaluated in the bot's configured timezone, not the repository's timezone. Set `"timezone"` explicitly to avoid off-by-one-day schedule surprises.

---

## Verification

```bash
# Validate renovate.json schema locally
npx --yes renovate-config-validator renovate.json

# Dry-run Renovate to preview generated PRs (requires RENOVATE_TOKEN)
LOG_LEVEL=debug npx --yes renovate \
  --platform=github \
  --token="$RENOVATE_TOKEN" \
  --dry-run=full \
  --print-config \
  your-org/your-repo 2>&1 | grep -E "groupName|packageName|automerge"
```

---

## Related

- `renovate-dependency-update-automation.md`
- `pnpm-catalogs-version-policy.md`
- `pnpm-workspace-setup.md`
- `changesets-monorepo-versioning.md`
- `wrangler-config-validation-ci.md`
- `lefthook-parallel-hooks-workers-ci.md`

---

## Sources

- Renovate `packageRules` docs: https://docs.renovatebot.com/configuration-options/#packagerules
- Renovate `groupName` / `groupSlug`: https://docs.renovatebot.com/configuration-options/#groupname
- Renovate `minimumReleaseAge`: https://docs.renovatebot.com/configuration-options/#minimumreleaseage
- Renovate presets: https://docs.renovatebot.com/presets-config/
- Cloudflare Workers changelog: https://developers.cloudflare.com/workers/platform/changelog/
