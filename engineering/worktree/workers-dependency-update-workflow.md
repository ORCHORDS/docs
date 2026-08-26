# Automated Dependency Update Workflow for Workers Projects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Dependencies in the Workers monorepo fall weeks or months behind. When `wrangler` is eventually updated manually, it introduces breaking changes to `wrangler.toml` syntax or `compatibility_date` requirements. D1 migrations may need to be re-run after a wrangler major update. You need a workflow that keeps dependencies fresh automatically with zero manual effort for low-risk updates, and a clear review gate for high-risk ones.

## Context

Renovate Bot (by Mend) reads dependency files (`package.json`, `wrangler.toml`, `Dockerfile`, GitHub Actions) and opens PRs for available updates. Unlike Dependabot, Renovate supports grouping, scheduling, automerge, and custom managers — critical for a Cloudflare Workers project where `wrangler` updates and `@cloudflare/workers-types` updates should always travel together. Renovate is configured via `renovate.json` at the repository root.

## Solution

**Install Renovate as a GitHub App** (free for public and private repos): https://github.com/apps/renovate

**`renovate.json`** — full configuration:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": [
    "config:recommended",
    "group:allNonMajor",
    ":dependencyDashboard",
    ":semanticCommits",
    ":separateMajorReleases",
    ":pinVersions"
  ],
  "schedule": ["before 6am on Monday"],
  "timezone": "Europe/Amsterdam",
  "labels": ["dependencies"],
  "assignees": ["@example-org/example-repo"],
  "reviewers": ["@example-org/example-repo"],
  "packageRules": [
    {
      "description": "Group all Cloudflare-related packages into one PR",
      "matchPackagePatterns": [
        "^wrangler$",
        "^@cloudflare/",
        "^miniflare$",
        "^@miniflare/"
      ],
      "groupName": "cloudflare-toolchain",
      "groupSlug": "cloudflare",
      "labels": ["dependencies", "cloudflare"],
      "reviewers": ["@example-org/example-repo"],
      "automerge": false,
      "prPriority": 10
    },
    {
      "description": "Automerge patch and minor updates for non-Cloudflare devDependencies",
      "matchDepTypes": ["devDependencies"],
      "matchUpdateTypes": ["patch", "minor"],
      "matchPackagePatterns": ["*"],
      "excludePackagePatterns": ["^wrangler$", "^@cloudflare/", "^miniflare$"],
      "automerge": true,
      "automergeType": "pr",
      "automergeStrategy": "squash",
      "requiredStatusChecks": null,
      "platformAutomerge": true
    },
    {
      "description": "Never automerge major updates — always require review",
      "matchUpdateTypes": ["major"],
      "automerge": false,
      "labels": ["dependencies", "breaking-change"],
      "prPriority": 20
    },
    {
      "description": "Turborepo updates: group and require manual review",
      "matchPackageNames": ["turbo"],
      "groupName": "turborepo",
      "automerge": false
    },
    {
      "description": "TypeScript: minor and patch only, require review",
      "matchPackageNames": ["typescript"],
      "matchUpdateTypes": ["minor", "patch"],
      "automerge": false,
      "labels": ["dependencies", "typescript"]
    },
    {
      "description": "GitHub Actions — pin to SHA and automerge patch",
      "matchManagers": ["github-actions"],
      "matchUpdateTypes": ["patch"],
      "automerge": true,
      "pinDigests": true
    },
    {
      "description": "Lock file maintenance — weekly Monday",
      "matchUpdateTypes": ["lockFileMaintenance"],
      "enabled": true,
      "schedule": ["before 4am on Monday"]
    }
  ],
  "lockFileMaintenance": {
    "enabled": true,
    "schedule": ["before 4am on Monday"]
  },
  "ignorePaths": [
    "**/node_modules/**",
    "**/dist/**",
    "**/.turbo/**"
  ],
  "vulnerabilityAlerts": {
    "enabled": true,
    "labels": ["security", "dependencies"],
    "automerge": true,
    "automergeType": "pr"
  },
  "prConcurrentLimit": 5,
  "prHourlyLimit": 2
}
```

**D1 migration safety check before wrangler update (`.github/workflows/wrangler-update-check.yml`):**

```yaml
name: Wrangler Update Safety Check

on:
  pull_request:
    paths:
      - 'package-lock.json'
      - 'package.json'
    branches:
      - main

jobs:
  wrangler-safety:
    if: contains(github.head_ref, 'renovate') && contains(github.head_ref, 'cloudflare')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - run: npm ci

      - name: Check wrangler version changed
        id: wrangler-version
        run: |
          OLD=$(git show origin/main:package-lock.json | jq -r '.packages["node_modules/wrangler"].version // "unknown"')
          NEW=$(jq -r '.packages["node_modules/wrangler"].version' package-lock.json)
          echo "old=$OLD" >> "$GITHUB_OUTPUT"
          echo "new=$NEW" >> "$GITHUB_OUTPUT"
          if [ "$OLD" != "$NEW" ]; then
            echo "changed=true" >> "$GITHUB_OUTPUT"
          else
            echo "changed=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Run D1 migration dry-run
        if: steps.wrangler-version.outputs.changed == 'true'
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
        run: |
          echo "Wrangler updated: ${{ steps.wrangler-version.outputs.old }} -> ${{ steps.wrangler-version.outputs.new }}"
          # Validate wrangler.toml syntax for all workers
          for dir in workers/*/; do
            if [ -f "$dir/wrangler.toml" ]; then
              echo "Validating $dir..."
              (cd "$dir" && npx wrangler deploy --dry-run --outdir /tmp/dryrun-$(basename $dir))
            fi
          done
          # List pending migrations to surface any schema changes
          npx wrangler d1 migrations list orchords-prod

      - name: Comment PR with wrangler diff
        if: steps.wrangler-version.outputs.changed == 'true'
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `**Wrangler version changed**: ${{ steps.wrangler-version.outputs.old }} → ${{ steps.wrangler-version.outputs.new }}\n\nD1 migration dry-run passed. Review wrangler CHANGELOG for breaking changes before merging.`
            })
```

**Major version review checklist (stored in `.github/PULL_REQUEST_TEMPLATE/major_dependency.md`):**

```markdown
## Major Dependency Update Checklist

- [ ] Read the package CHANGELOG / migration guide
- [ ] Confirmed no breaking changes to `wrangler.toml` syntax
- [ ] Confirmed `compatibility_date` does not need to be bumped
- [ ] Ran `wrangler deploy --dry-run` for all workers locally
- [ ] Checked for TypeScript type errors after update
- [ ] Tested in staging environment (`wrangler deploy --env staging`)
- [ ] Reviewed D1 migrations (if wrangler major version)
- [ ] Updated any affected `turbo.json` task configurations
```

**Local Renovate dry-run (for testing config changes):**

```bash
# Install Renovate CLI
npm install -g renovate

# Dry-run against the repo (no PRs created)
LOG_LEVEL=debug renovate \
  --platform=local \
  --dry-run=lookup \
  --repository-cache=reset

# Validate renovate.json schema
npx --package renovate -- renovate-config-validator renovate.json
```

## Implementation Details

- `"extends": ["config:recommended"]` enables Renovate's default ruleset, which includes sensible defaults for most package managers. Custom `packageRules` in the same config override or extend these defaults — later rules take precedence when multiple rules match a package.
- `"automergeStrategy": "squash"` squashes the Renovate PR's commits into one, keeping the `main` history clean. Combined with `"automergeType": "pr"`, Renovate waits for all required status checks to pass before merging — it does not merge if CI is red.
- `"prConcurrentLimit": 5` prevents Renovate from flooding the repository with dozens of PRs on its first run. `"prHourlyLimit": 2` adds a rate limit to avoid overwhelming reviewers.
- `"pinDigests": true` for GitHub Actions pins action steps to their commit SHA rather than a mutable tag. This prevents supply-chain attacks where a tag like `actions/checkout@v4` is moved to a malicious commit.
- `"vulnerabilityAlerts"` instructs Renovate to open immediate PRs for packages with known CVEs, bypassing the normal Monday schedule.

## Anti-patterns

- **Automerging `wrangler` updates**: Wrangler updates can change `wrangler.toml` syntax, D1 API behaviour, or runtime compatibility. Always require manual review for cloudflare-toolchain updates.
- **No `prConcurrentLimit`**: Without a limit, the first Renovate run on a repo that has not been updated in months can open 50+ PRs simultaneously, making them impossible to review.
- **Ignoring lock file maintenance**: The `lockFileMaintenance` PR re-locks all transitive dependencies to their latest patch versions. Skipping it allows transitive vulnerabilities to accumulate.
- **Using `"extends": [":pinVersions"]` for Workers runtime dependencies**: Pinning exact versions for `wrangler` and `@cloudflare/workers-types` is fine, but pinning runtime `dependencies` in a Worker is unnecessary (Workers bundle everything, there is no install step at runtime).

## Gotchas

- Renovate's `schedule` is evaluated in the timezone specified by `"timezone"`. If the server Renovate runs on is in UTC, the schedule is still applied correctly based on the configured timezone — but verify this in the Renovate dashboard.
- `"platformAutomerge": true` uses GitHub's native auto-merge feature, which requires branch protection rules to have at least one required status check. Without required checks, GitHub will merge immediately without waiting for CI.
- Renovate does not update `wrangler.toml`'s `compatibility_date` field automatically. If a major wrangler update requires a newer `compatibility_date`, this must be changed manually.
- In monorepos with npm workspaces, Renovate updates `package-lock.json` at the root. Ensure the lockfile is not `.gitignore`d.

## Verification

```bash
# Validate Renovate config
npx --package renovate -- renovate-config-validator renovate.json
# Expected: config is valid

# Check which packages Renovate would update
LOG_LEVEL=info renovate --platform=local --dry-run=lookup 2>&1 | grep 'update'

# After automerge, verify the Worker still deploys
cd workers/api-gateway && npx wrangler deploy --dry-run --outdir /tmp/post-renovate-dryrun

# Check dependency dashboard issue in GitHub
# Renovate creates/updates an issue titled 'Dependency Dashboard' automatically
```

## Related

- `workers-monorepo-turborepo-setup.md` — Turborepo and wrangler interact during deploys
- `workers-git-hooks-husky-setup.md` — pre-push hook catches broken bundles from bad updates
- `workers-semantic-versioning-automation.md` — Renovate PRs trigger conventional-commit-based releases
- `merge-queue-github-actions.md` — automerge PRs flow through the merge queue

## Sources

- https://docs.renovatebot.com/configuration-options/
- https://docs.renovatebot.com/presets-config/
- https://docs.renovatebot.com/modules/manager/github-actions/
- https://developers.cloudflare.com/workers/wrangler/migration/
