# Renovate Bot Automerge for Cloudflare Workers Dependencies

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Dependency PRs for `wrangler`, `@cloudflare/workers-types`, and `hono` pile up in your monorepo because the team lacks bandwidth to review them manually. You want Renovate to automerge these updates when CI passes, but without blindly merging zero-day releases that may introduce breaking API changes or supply-chain issues.

## Context

Renovate Bot supports per-package automerge rules through `packageRules`. The key safety levers are `minimumReleaseAge` (wait N days after a package version is published before considering it for automerge) and `automergeType` (choose between branch-level silent merge or PR-level merge). Cloudflare Workers projects also pin a `compatibility_date` in `wrangler.toml`; Renovate cannot update that field natively, but a `postUpgradeTasks` hook can run `wrangler types` to regenerate type stubs after a `@cloudflare/workers-types` bump. All automerges must be gated on a green CI run.

## Renovate Config

Place this at the repository root as `renovate.json` (or merge into an existing config):

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended"],
  "automerge": false,
  "automergeType": "pr",
  "automergeStrategy": "squash",
  "platformAutomerge": true,
  "minimumReleaseAge": "3 days",
  "stabilityDays": 3,
  "prConcurrentLimit": 5,
  "branchConcurrentLimit": 10,
  "packageRules": [
    {
      "description": "Automerge Wrangler patch and minor updates",
      "matchPackageNames": ["wrangler"],
      "matchUpdateTypes": ["patch", "minor"],
      "automerge": true,
      "minimumReleaseAge": "3 days",
      "postUpgradeTasks": {
        "commands": ["pnpm exec wrangler types"],
        "fileFilters": ["**/*.d.ts", "worker-configuration.d.ts"],
        "executionMode": "branch"
      }
    },
    {
      "description": "Automerge @cloudflare/workers-types minor/patch",
      "matchPackageNames": ["@cloudflare/workers-types"],
      "matchUpdateTypes": ["patch", "minor"],
      "automerge": true,
      "minimumReleaseAge": "3 days",
      "postUpgradeTasks": {
        "commands": ["pnpm exec wrangler types"],
        "fileFilters": ["worker-configuration.d.ts", "**/*.d.ts"],
        "executionMode": "branch"
      }
    },
    {
      "description": "Automerge Hono patch updates; require manual review for minor+",
      "matchPackageNames": ["hono"],
      "matchUpdateTypes": ["patch"],
      "automerge": true,
      "minimumReleaseAge": "3 days"
    },
    {
      "description": "Never automerge major updates for Workers toolchain",
      "matchPackageNames": ["wrangler", "@cloudflare/workers-types", "hono"],
      "matchUpdateTypes": ["major"],
      "automerge": false,
      "labels": ["needs-review", "major-update"]
    },
    {
      "description": "Pin compatibility_date updates to a separate PR for manual review",
      "matchDepTypes": ["compatibilityDate"],
      "automerge": false,
      "labels": ["compatibility-date", "needs-review"]
    }
  ]
}
```

## CI Gate Configuration

Automerge is only safe when CI is authoritative. Ensure your branch protection requires these status checks before merge:

```yaml
# .github/branch-protection.yml (managed via Terraform or gh CLI)
# Equivalent gh CLI:
# gh api repos/example-org/example-repo/branches/main/protection \
#   --method PUT --input branch-protection.json
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "build",
      "typecheck",
      "test",
      "deploy / dry-run"
    ]
  },
  "required_pull_request_reviews": null,
  "enforce_admins": false,
  "restrictions": null
}
```

In your CI workflow, add a `wrangler types` check step:

```yaml
# .github/workflows/ci.yml (excerpt)
- name: Regenerate wrangler types
  run: pnpm exec wrangler types
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

- name: Check for type drift
  run: |
    git diff --exit-code -- '*.d.ts' || {
      echo "ERROR: wrangler types output differs from committed stubs."
      echo "Run 'pnpm exec wrangler types' locally and commit the result."
      exit 1
    }
```

## Pinning compatibility_date via Wrangler.toml

Renovate cannot parse `wrangler.toml` natively, but you can expose the date as a package-like dependency using a custom manager:

```json
{
  "customManagers": [
    {
      "customType": "regex",
      "fileMatch": ["(^|/)wrangler\\.toml$"],
      "matchStrings": [
        "compatibility_date\\s*=\\s*\"(?<currentValue>[0-9]{4}-[0-9]{2}-[0-9]{2})\""
      ],
      "datasourceTemplate": "custom.cloudflare-compat-date",
      "depNameTemplate": "cloudflare-compatibility-date",
      "versioningTemplate": "loose"
    }
  ]
}
```

Alternatively, track it manually and use Renovate labels to flag PRs that touch `wrangler.toml`.

## postUpgradeTasks for Type Regeneration

When `@cloudflare/workers-types` bumps, the generated `worker-configuration.d.ts` must be refreshed. The `postUpgradeTasks` block runs in the Renovate environment (requires `allowedPostUpgradeCommands` in the Renovate global config or self-hosted config):

```json
// In your self-hosted renovate config (config.js)
module.exports = {
  allowedPostUpgradeCommands: [
    "^pnpm exec wrangler types$",
    "^pnpm install --frozen-lockfile$"
  ]
};
```

Confirm the task ran by inspecting the Renovate PR description — it appends a log section showing command output.

## Anti-patterns

- **Setting `automerge: true` globally** — catches non-Workers packages (React, Vite, etc.) that need human review for minor/major bumps.
- **Skipping `minimumReleaseAge`** — a zero-day typosquatting release or accidental publish gets automerged before the community notices.
- **Not pinning `platformAutomerge: true`** — without it, Renovate merges via API even when GitHub's merge queue is configured, bypassing the queue's additional checks.
- **Allowing `postUpgradeTasks` without `allowedPostUpgradeCommands` allowlist** — untrusted `postUpgradeTasks` commands could run arbitrary code in your CI environment.
- **Forgetting `branchConcurrentLimit`** — Renovate creates one branch per update; without a cap it can open dozens simultaneously and saturate your runner pool.

## Gotchas

- `minimumReleaseAge` is evaluated against npm publish time, not GitHub release time; the two can differ by hours.
- `stabilityDays` and `minimumReleaseAge` serve the same purpose with different semantics; setting both is redundant — pick one (`minimumReleaseAge` is more explicit).
- `postUpgradeTasks` only runs in self-hosted Renovate; GitHub App hosted Renovate does not execute arbitrary shell commands.
- `platformAutomerge: true` delegates the actual merge to GitHub's merge API; it respects required status checks but ignores Renovate's own `automergeSchedule`.
- The `compatibilityDate` `matchDepTypes` filter is a placeholder — Renovate does not have a built-in `compatibilityDate` dep type; use the custom manager regex approach instead.

## Verification

```bash
# Simulate Renovate locally with the config validator
npx --yes renovate-config-validator renovate.json

# Dry-run Renovate against the repo (self-hosted)
renovate --dry-run=full --print-config example-org/example-repo 2>&1 | \
  grep -E '(automerge|minimumReleaseAge|postUpgrade)'

# Check which PRs Renovate would open right now
renovate --dry-run=lookup example-org/example-repo 2>&1 | grep 'PR:'

# Verify wrangler types regeneration works locally
pnpm exec wrangler types
git diff --stat
```

## Related

- `turborepo-affected-package-workers-deploy-gate.md`
- `pnpm-recursive-exec-workers-monorepo-build.md`

## Sources

- Renovate automerge documentation — https://docs.renovatebot.com/configuration-options/#automerge
- Renovate postUpgradeTasks — https://docs.renovatebot.com/configuration-options/#postupgradetasks
- Renovate minimumReleaseAge — https://docs.renovatebot.com/configuration-options/#minimumreleaseage
- Wrangler types command — https://developers.cloudflare.com/workers/wrangler/commands/#types
