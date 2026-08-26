# Keeping Wrangler and Workers Dependencies Updated with Dependabot

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Workers project is pinned to an older version of Wrangler because no one has time to manually check for updates. This leads to:
- Missing security patches in the Wrangler CLI
- Missing support for new Workers runtime APIs that require a minimum Wrangler version
- Subtle compatibility issues when a developer upgrades locally but CI still uses an old pinned version
- Accumulated npm dependency drift making future upgrades painful

The team wants automated PRs for dependency updates, with patch-level changes merged automatically and major version changes reviewed manually.

---

## Context

Dependabot is GitHub's built-in dependency update service. It opens pull requests that bump specific packages, respecting semantic versioning, and can be configured to:
- Group related packages into a single PR (e.g., all `@cloudflare/*` packages)
- Auto-merge patch and minor updates that pass CI
- Hold major version updates in a separate PR for manual review
- Run on a defined schedule to avoid PR noise

For Workers projects, Wrangler updates deserve special attention because:
- Wrangler minor versions frequently introduce new `wrangler.toml` fields
- The `@cloudflare/workers-types` package must stay in sync with the deployed runtime
- Some Wrangler major bumps change the CLI command surface (e.g., `wrangler publish` → `wrangler deploy`)

---

## Solution

### 1. .github/dependabot.yml

```yaml
version: 2
updates:
  # npm ecosystem — Workers project dependencies
  - package-ecosystem: npm
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
      timezone: Europe/Berlin
    open-pull-requests-limit: 10
    target-branch: main

    # Group Wrangler and Cloudflare tooling into one PR
    groups:
      cloudflare-tooling:
        patterns:
          - "wrangler"
          - "@cloudflare/*"
          - "miniflare"
        update-types:
          - minor
          - patch

      # Group test tooling separately
      test-tooling:
        patterns:
          - "vitest"
          - "@vitest/*"
          - "@cloudflare/vitest-pool-workers"
        update-types:
          - minor
          - patch

    # Hold major version bumps on packages that require migration planning
    ignore:
      - dependency-name: "wrangler"
        update-types: ["version-update:semver-major"]
      - dependency-name: "@cloudflare/workers-types"
        update-types: ["version-update:semver-major"]
      - dependency-name: "@biomejs/biome"
        update-types: ["version-update:semver-major"]

    labels:
      - dependencies
      - automated

    commit-message:
      prefix: chore
      prefix-development: chore
      include: scope

  # GitHub Actions dependencies
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: monthly
    groups:
      actions:
        patterns:
          - "*"
    labels:
      - dependencies
      - github-actions
```

### 2. Auto-merge workflow for patch updates

```yaml
# .github/workflows/auto-merge-dependabot.yml
name: Auto-merge Dependabot PRs

on:
  pull_request:

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    if: github.actor == 'dependabot[bot]'
    steps:
      - name: Fetch Dependabot metadata
        id: meta
        uses: dependabot/fetch-metadata@v2
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Auto-merge patch updates
        if: |
          steps.meta.outputs.update-type == 'version-update:semver-patch' &&
          steps.meta.outputs.dependency-names != 'wrangler'
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Auto-merge minor Cloudflare tooling updates
        if: |
          steps.meta.outputs.update-type == 'version-update:semver-minor' &&
          contains(steps.meta.outputs.dependency-names, 'wrangler')
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`--auto` flag enables merge only after all required status checks pass, preventing auto-merge from bypassing CI.

### 3. CI compatibility check on Dependabot PRs

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci

      - name: Type check
        run: npx tsc --noEmit

      - name: Lint
        run: npx @biomejs/biome ci ./src

      - name: Unit tests
        run: npx vitest run

      - name: Wrangler dry-run deploy
        run: npx wrangler deploy --dry-run --outdir dist
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

The `wrangler deploy --dry-run` step is critical for Dependabot PRs: it validates that the new Wrangler version can still parse `wrangler.toml` and bundle `src/index.ts` without a real deploy.

### 4. Verifying `@cloudflare/workers-types` compatibility

When Dependabot bumps `@cloudflare/workers-types`, a TypeScript check catches any removed or renamed runtime APIs:

```typescript
// src/__tests__/types.test-d.ts
import { expectTypeOf, test } from "vitest";

test("Workers runtime types are intact", () => {
    // Verify key APIs are still typed correctly after a workers-types update
    expectTypeOf<KVNamespace["get"]>().toBeFunction();
    expectTypeOf<R2Bucket["get"]>().toBeFunction();
    expectTypeOf<DurableObjectNamespace["get"]>().toBeFunction();
    expectTypeOf<Queue["send"]>().toBeFunction();
});
```

```bash
npx vitest run --typecheck
```

### 5. Tracking Wrangler versions in wrangler.toml

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]

# Pin the minimum Wrangler version required for this config
# (informational — not enforced by Wrangler itself)
# min_wrangler_version = "3.65.0"
```

The `compatibility_date` in `wrangler.toml` is separate from the Wrangler CLI version. Bumping the compatibility date opts into new runtime behaviours and should be a deliberate change, not an automatic one.

---

## Implementation Details

### Dependabot PR grouping behaviour

Grouped PRs open one PR for all packages in the group. If any package in the group cannot be resolved, the entire group PR is skipped. Monitor the Dependabot "Insights" tab for skipped updates.

### Rate limits

Dependabot creates at most `open-pull-requests-limit` concurrent PRs (default 5, shown as 10 above). When the limit is reached, Dependabot queues updates and opens new PRs as existing ones are merged or closed.

### Private packages

For Workers projects that depend on private npm packages (e.g., internal shared middleware), add a `registries` block:

```yaml
registries:
  npm-private:
    type: npm-registry
    url: https://registry.npmjs.org
    token: ${{ secrets.NPM_TOKEN }}

updates:
  - package-ecosystem: npm
    directory: /
    registries:
      - npm-private
```

---

## Anti-patterns

- **Auto-merging `wrangler` major updates.** Wrangler major bumps (e.g., v3 → v4) often require `wrangler.toml` changes or command renames. Always review these manually.
- **Setting `open-pull-requests-limit: 0`.** This disables Dependabot entirely. Use `ignore` rules for packages you cannot update right now instead of disabling the whole service.
- **Ignoring `@cloudflare/workers-types` updates.** Types drift from the actual runtime. An outdated `workers-types` package means TypeScript cannot warn you about deprecated or removed APIs.
- **Not running `wrangler deploy --dry-run` on Dependabot PRs.** A passing unit test suite does not guarantee the bundler still works after a Wrangler update.

---

## Gotchas

- Dependabot reads `package-lock.json` (npm), `yarn.lock`, or `pnpm-lock.yaml`. If the lockfile is absent or gitignored, Dependabot cannot open PRs.
- The `commit-message.include: scope` option in Dependabot config makes commits Conventional Commit-compatible (e.g., `chore(deps): bump wrangler from 3.64.0 to 3.65.0`). This integrates cleanly with Release Please.
- GitHub's auto-merge requires branch protection rules with at least one required status check. Without a required check, `gh pr merge --auto` merges immediately, bypassing CI.
- Dependabot PRs from forked repos do not have access to repository secrets, so the `CLOUDFLARE_API_TOKEN` used in the dry-run step is unavailable. Use `pull_request_target` with explicit secret injection for fork support — but be aware of the security implications.

---

## Verification

```bash
# Confirm dependabot.yml is valid YAML
npx js-yaml .github/dependabot.yml > /dev/null && echo "Valid"

# Inspect currently open Dependabot PRs
gh pr list --author "app/dependabot" --label dependencies

# Check auto-merge status on a specific PR
gh pr view 123 --json autoMergeRequest

# Manually trigger a Dependabot run (requires GitHub CLI with dependabot extension)
gh dependabot check-for-updates --repo example-org/example-repo
```

---

## Related

- `documentation/docs/policies/devtools/workers-release-please-automation.md`
- `documentation/docs/policies/devtools/workers-biome-linter-formatter.md`
- `documentation/ci/workers-github-actions-deploy.md`

---

## Sources

- https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file
- https://github.com/dependabot/fetch-metadata
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
