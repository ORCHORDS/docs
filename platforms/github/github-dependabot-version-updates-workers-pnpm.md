# Dependabot Version Updates: Workers pnpm

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Workers monorepo managed with pnpm workspaces has Dependabot enabled but receives no
version-update PRs for worker-level packages. The root `package.json` declares workspaces but
`dependabot.yml` only lists a single `npm` entry pointing to `/`. Dependabot does not crawl pnpm
workspace members automatically — each package directory needs an explicit entry. Major `wrangler`
bumps also land silently because no ignore rule is in place, breaking deploys when a CLI flag
changed.

## Context

A typical Workers monorepo with pnpm workspaces:

```
/
├── apps/
│   ├── api-worker/package.json
│   └── edge-worker/package.json
├── packages/
│   ├── shared/package.json
│   └── db-client/package.json
├── package.json          ← workspace root
└── pnpm-workspace.yaml
```

Dependabot supports pnpm lock files since mid-2024 when `package-ecosystem: npm` is used. It reads
`pnpm-lock.yaml` in preference to `package-lock.json` when both are present. There is no
`package-ecosystem: pnpm` — always use `npm`.

Key behaviours to account for:
- One `directory` entry per workspace member; a single `/` entry covers only the root.
- `groups` reduce PR volume by batching related packages together.
- `ignore` rules on `wrangler` major bumps protect `wrangler.toml` `compatibility_date` semantics.
- `--frozen-lockfile` in CI must be relaxed to `--frozen-lockfile=false` for Dependabot PRs
  because Dependabot generates a new `pnpm-lock.yaml` that `--frozen-lockfile` refuses to accept.

## dependabot.yml Configuration

```yaml
# .github/dependabot.yml
version: 2

updates:
  # ── Workspace root ──────────────────────────────────────────────────────────
  - package-ecosystem: npm
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "09:00"
      timezone: Europe/London
    groups:
      cloudflare-workers:
        patterns:
          - "wrangler"
          - "@cloudflare/*"
          - "miniflare"
      typescript-toolchain:
        patterns:
          - "typescript"
          - "tsx"
          - "vitest"
          - "@vitest/*"
    ignore:
      # Major wrangler bumps need manual review: compatibility_date semantics
      # and removed CLI flags change between major versions.
      - dependency-name: wrangler
        update-types: ["version-update:semver-major"]

  # ── apps/api-worker ─────────────────────────────────────────────────────────
  - package-ecosystem: npm
    directory: /apps/api-worker
    schedule:
      interval: weekly
      day: monday
      time: "09:00"
      timezone: Europe/London
    groups:
      hono:
        patterns: ["hono", "@hono/*"]
      validation:
        patterns: ["zod", "valibot"]

  # ── apps/edge-worker ────────────────────────────────────────────────────────
  - package-ecosystem: npm
    directory: /apps/edge-worker
    schedule:
      interval: weekly
      day: monday
      time: "09:30"
      timezone: Europe/London

  # ── packages/db-client ──────────────────────────────────────────────────────
  - package-ecosystem: npm
    directory: /packages/db-client
    schedule:
      interval: weekly
      day: tuesday
      time: "09:00"
      timezone: Europe/London

  # ── packages/shared ─────────────────────────────────────────────────────────
  - package-ecosystem: npm
    directory: /packages/shared
    schedule:
      interval: weekly
      day: tuesday
      time: "09:00"
      timezone: Europe/London

  # ── GitHub Actions ──────────────────────────────────────────────────────────
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "08:00"
      timezone: Europe/London
    groups:
      actions:
        patterns: ["*"]
```

## Auto-merge Workflow

```yaml
# .github/workflows/dependabot-auto-merge.yml
name: Dependabot Auto-merge
on: pull_request

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-merge:
    if: github.actor == 'dependabot[bot]'
    runs-on: ubuntu-latest
    steps:
      - name: Fetch Dependabot metadata
        id: meta
        uses: dependabot/fetch-metadata@v2
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Auto-merge patch and minor updates
        if: |
          steps.meta.outputs.update-type == 'version-update:semver-patch' ||
          steps.meta.outputs.update-type == 'version-update:semver-minor'
        run: gh pr merge --auto --squash "${{ github.event.pull_request.html_url }}"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Validating Dependabot PRs Against Workers Type-checking

Run a targeted validation job on Dependabot PRs to catch type breaks from `wrangler` or
`@cloudflare/workers-types` bumps before auto-merge fires.

```typescript
// scripts/validate-dependabot-update.ts
import { execSync } from "node:child_process";

const changedPackages = process.env.DEPENDABOT_CHANGED_PACKAGES ?? "";

function run(cmd: string): void {
  console.log(`> ${cmd}`);
  execSync(cmd, { stdio: "inherit" });
}

// Dependabot generates a new lockfile; must use --frozen-lockfile=false
run("pnpm install --frozen-lockfile=false");

// Always typecheck all workers
run("pnpm --filter='./apps/*' --filter='./packages/*' exec tsc --noEmit");

if (changedPackages.includes("wrangler")) {
  console.log("wrangler updated — running dry-run deploy checks");
  run("pnpm --filter='./apps/*' exec wrangler deploy --dry-run");
}

if (changedPackages.includes("@cloudflare/")) {
  console.log("@cloudflare/* updated — running unit tests");
  run("pnpm --filter='./apps/*' vitest run");
}

console.log("Validation passed");
```

```yaml
# In the CI workflow, add a job that only runs for Dependabot PRs:
  validate-dependabot:
    if: github.actor == 'dependabot[bot]'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - name: Fetch metadata
        id: meta
        uses: dependabot/fetch-metadata@v2
        with: { github-token: "${{ secrets.GITHUB_TOKEN }}" }
      - name: Validate update
        run: pnpm tsx scripts/validate-dependabot-update.ts
        env:
          DEPENDABOT_CHANGED_PACKAGES: ${{ steps.meta.outputs.dependency-names }}
```

## Pinning compatibility_date Independently of Wrangler Bumps

Wrangler major versions sometimes ship a newer default `compatibility_date`. Pin the date
explicitly in each worker's `wrangler.toml` so a Dependabot wrangler bump never silently enables
new runtime behaviour.

```toml
# apps/api-worker/wrangler.toml
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"
# Bump this date deliberately after reviewing the compatibility changelog,
# not automatically via any dependency update.
```

Add a CI check that ensures `compatibility_date` was not modified by the Dependabot PR:

```typescript
// scripts/check-compatibility-date.ts
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Only enforce on Dependabot PRs
if (process.env.GITHUB_ACTOR !== "dependabot[bot]") process.exit(0);

const diff = execSync("git diff origin/main -- '**/wrangler.toml'").toString();
if (diff.includes("compatibility_date")) {
  console.error(
    "ERROR: A Dependabot PR must not modify compatibility_date in wrangler.toml.\n" +
      "Update compatibility_date manually after reviewing the changelog."
  );
  process.exit(1);
}

console.log("compatibility_date unchanged — OK");
```

## Anti-patterns

- A single `directory: /` entry covering the entire monorepo — Dependabot only reads the root
  `package.json` and misses `devDependencies` and dependencies declared only in workspace members.
- Using `package-ecosystem: pnpm` — this is not a valid ecosystem type; Dependabot will silently
  ignore the entry. Always use `npm`.
- Auto-merging major `wrangler` updates — major versions change CLI flag names, remove deprecated
  `wrangler.toml` keys, and can shift default compatibility dates in ways that break deploys.
- Grouping `@cloudflare/*` and `wrangler` into one auto-merge group — `wrangler` is the deploy
  CLI; `@cloudflare/workers-types` is type definitions. They lag each other and have independent
  risk profiles.

## Gotchas

- Dependabot opens a separate PR per `directory` entry even when the same package appears in
  multiple workspace members. A bump to `zod` can generate five PRs in one week. Use `groups` to
  batch packages that always move together; this reduces but does not eliminate multiple PRs.
- `pnpm install --frozen-lockfile` rejects Dependabot's regenerated `pnpm-lock.yaml`. Gate the
  frozen-lockfile flag on whether `GITHUB_ACTOR === 'dependabot[bot]'`, or use a separate CI job
  that passes `--frozen-lockfile=false` only for Dependabot PRs.
- GitHub's merge queue does not auto-enqueue Dependabot PRs. If your branch protection requires
  the merge queue, add a workflow step that calls `gh pr merge --auto` to enqueue Dependabot PRs
  after the auto-approve step.
- `schedule.day` is honoured only for `interval: weekly`. For `interval: daily` Dependabot
  ignores the `day` field; set the time carefully to avoid peak-traffic deploys.

## Verification

```bash
# Confirm which workspace directories Dependabot is tracking
gh api repos/:owner/:repo/dependabot/alerts \
  --jq '[.[].dependency.manifest_path] | unique | sort'

# List open Dependabot PRs with their update types
gh pr list \
  --app dependabot \
  --json number,title,labels \
  --jq '.[] | "\(.number): \(.title) [\(.labels | map(.name) | join(", "))]"'

# Confirm pnpm-lock.yaml is being updated (not package-lock.json)
gh pr view <pr-number> --json files \
  --jq '.files[].path' | grep lock
```

## Related

- `dependabot-auto-merge-workers-deps.md`
- `dependabot-config.md`
- `dependabot-vs-renovate-2026.md`
- `dependabot-multi-ecosystem-group-review-boundary.md`
- `github-actions-cache-pnpm-turbo.md`

## Sources

- https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file
- https://docs.github.com/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- https://pnpm.io/workspaces
