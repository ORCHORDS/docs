# Monorepo Change Detection for Selective Wrangler Deploys

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

---

## Symptom / Use-case

A Cloudflare Workers monorepo contains ten Workers: `api-gateway`, `auth`, `media-upload`,
`billing`, `search`, `notifications`, `analytics-ingest`, `admin-api`, `webhook-router`, and
`cron-jobs`. A PR that changes only `packages/search/` triggers the full `wrangler deploy`
pipeline for all ten Workers—an eight-minute CI job that deploys nine unchanged Workers
needlessly, consumes rate-limit budget, and blocks the deploy pipeline behind it. You need a
change detection layer that maps each changed file to the Worker(s) that depend on it and
deploys only those Workers.

---

## Context

Wrangler requires one deploy command per Worker (`wrangler deploy --config wrangler.toml`).
In a monorepo each Worker lives in its own directory with its own `wrangler.toml`. Shared
code (types, utilities, D1 query helpers) lives in `packages/` and is consumed by multiple
Workers. The change detection problem is:

> Given the set of files changed between `HEAD` and `origin/main`, which Workers need to be
> redeployed?

Two approaches are common:

1. **File-path-based mapping** (simple, fast): a JSON config maps directory globs to Worker
   names. No graph analysis. Works for most monorepos.
2. **Dependency-graph-based detection** (precise, complex): use `pnpm` workspace graph or
   `turbo run deploy --filter=[HEAD^1]` to let the build tool determine what changed.

This article covers both, with a focus on the file-path mapping approach that integrates
directly with GitHub Actions without requiring Turborepo or Nx.

---

## Repository Layout

```
.
├── workers/
│   ├── api-gateway/
│   │   ├── wrangler.toml
│   │   └── src/
│   ├── auth/
│   │   ├── wrangler.toml
│   │   └── src/
│   └── search/
│       ├── wrangler.toml
│       └── src/
├── packages/
│   ├── db/          # shared D1 helpers — used by api-gateway, auth
│   ├── types/       # shared TypeScript types — used by all workers
│   └── config/      # runtime config helpers — used by all workers
├── .github/
│   └── deploy-map.json
└── package.json
```

---

## Dependency Map File

```json
// .github/deploy-map.json
{
  "_comment": "Maps file glob patterns to the Worker dirs that must be redeployed.",
  "rules": [
    {
      "pattern": "workers/api-gateway/**",
      "workers": ["workers/api-gateway"]
    },
    {
      "pattern": "workers/auth/**",
      "workers": ["workers/auth"]
    },
    {
      "pattern": "workers/search/**",
      "workers": ["workers/search"]
    },
    {
      "pattern": "packages/db/**",
      "workers": ["workers/api-gateway", "workers/auth"]
    },
    {
      "pattern": "packages/types/**",
      "workers": [
        "workers/api-gateway",
        "workers/auth",
        "workers/search"
      ]
    },
    {
      "pattern": "packages/config/**",
      "workers": [
        "workers/api-gateway",
        "workers/auth",
        "workers/search"
      ]
    },
    {
      "pattern": "pnpm-lock.yaml",
      "workers": "__ALL__"
    },
    {
      "pattern": "package.json",
      "workers": "__ALL__"
    }
  ],
  "all_workers": [
    "workers/api-gateway",
    "workers/auth",
    "workers/search"
  ]
}
```

`__ALL__` is a sentinel meaning "redeploy everything" — used for lockfile or root
`package.json` changes that may affect any Worker's bundled dependencies.

---

## Change Detection Script

```bash
#!/usr/bin/env bash
# scripts/affected-workers.sh
# Outputs newline-separated list of Worker directories to deploy.
# Usage: bash scripts/affected-workers.sh [base-ref]

set -euo pipefail

BASE_REF="${1:-origin/main}"
MAP_FILE=".github/deploy-map.json"

# Get changed files between base and HEAD
CHANGED=$(git diff --name-only "$BASE_REF"...HEAD)

if [[ -z "$CHANGED" ]]; then
  echo "No changes detected." >&2
  exit 0
fi

ALL_WORKERS=$(jq -r '.all_workers[]' "$MAP_FILE")

# Collect affected workers (deduplicated)
declare -A AFFECTED

while IFS= read -r file; do
  rule_count=$(jq '.rules | length' "$MAP_FILE")
  for (( i=0; i<rule_count; i++ )); do
    pattern=$(jq -r ".rules[$i].pattern" "$MAP_FILE")
    workers_raw=$(jq -c ".rules[$i].workers" "$MAP_FILE")

    # Use bash glob-style matching via fnmatch (case sensitive)
    if [[ "$file" == $pattern ]] 2>/dev/null || \
       echo "$file" | grep -qP "^${pattern//\*\*/.*}$" 2>/dev/null; then

      if [[ "$workers_raw" == '"__ALL__"' ]]; then
        # Deploy everything
        while IFS= read -r w; do AFFECTED["$w"]=1; done <<< "$ALL_WORKERS"
        break 2    # no need to check further
      else
        while IFS= read -r w; do
          AFFECTED["$w"]=1
        done < <(echo "$workers_raw" | jq -r '.[]')
      fi
    fi
  done
done <<< "$CHANGED"

# Output unique list
for w in "${!AFFECTED[@]}"; do
  echo "$w"
done
```

---

## GitHub Actions Workflow

```yaml
# .github/workflows/deploy-workers.yml
name: Selective Workers Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      force_all:
        description: 'Deploy all workers regardless of changes'
        type: boolean
        default: false

permissions:
  contents: read
  deployments: write

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.detect.outputs.matrix }}
      any_changes: ${{ steps.detect.outputs.any_changes }}

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Detect affected workers
        id: detect
        run: |
          if [[ "${{ github.event.inputs.force_all }}" == "true" ]]; then
            WORKERS=$(jq -c '.all_workers' .github/deploy-map.json)
          else
            WORKERS=$(bash scripts/affected-workers.sh origin/main^ | \
              jq -Rnc '[inputs]')
          fi

          echo "Affected workers: $WORKERS"

          if [[ "$WORKERS" == "[]" || -z "$WORKERS" ]]; then
            echo "any_changes=false" >> "$GITHUB_OUTPUT"
            echo "matrix={\"worker\":[]}" >> "$GITHUB_OUTPUT"
          else
            echo "any_changes=true" >> "$GITHUB_OUTPUT"
            echo "matrix={\"worker\":$WORKERS}" >> "$GITHUB_OUTPUT"
          fi

  deploy:
    needs: detect-changes
    if: needs.detect-changes.outputs.any_changes == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.detect-changes.outputs.matrix) }}
      fail-fast: false    # continue deploying other workers if one fails
      max-parallel: 3     # respect Wrangler API rate limits

    name: Deploy ${{ matrix.worker }}

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Deploy Worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          echo "Deploying ${{ matrix.worker }}"
          pnpm exec wrangler deploy \
            --config "${{ matrix.worker }}/wrangler.toml" \
            --env production

      - name: Record deployment
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.repos.createDeployment({
              ...context.repo,
              ref: context.sha,
              environment: 'production',
              description: 'Deploy ${{ matrix.worker }}',
              auto_merge: false,
              required_contexts: [],
            });

  notify-skipped:
    needs: detect-changes
    if: needs.detect-changes.outputs.any_changes == 'false'
    runs-on: ubuntu-latest
    steps:
      - run: echo "No Workers affected by this push. Deploy skipped."
```

---

## Turborepo Integration (Alternative)

If the monorepo uses Turborepo, delegate change detection to `turbo`:

```json
// turbo.json
{
  "tasks": {
    "deploy": {
      "dependsOn": ["^build"],
      "outputs": [],
      "cache": false
    }
  }
}
```

Each Worker's `package.json`:

```json
{
  "name": "@example-org/example-repo",
  "scripts": {
    "deploy": "wrangler deploy --config wrangler.toml --env production"
  }
}
```

CI command:

```bash
# Deploy only packages affected since the last successful deploy tag
pnpm exec turbo run deploy \
  --filter='...[origin/main]' \
  --concurrency=3
```

`turbo` resolves the workspace dependency graph automatically: if `packages/db` changed and
`workers/api-gateway` depends on it, `workers/api-gateway` is included.

---

## Maintaining the Dependency Map

The `deploy-map.json` file is the single source of truth for the file→Worker mapping. It
must be updated whenever:

- A new Worker is added to the monorepo.
- A new shared package is created.
- A Worker begins importing from a previously unrelated package.

Add a CI lint step to catch stale entries:

```bash
# scripts/lint-deploy-map.sh
# Checks that every directory in 'all_workers' exists and has a wrangler.toml.
ALL_WORKERS=$(jq -r '.all_workers[]' .github/deploy-map.json)
FAILED=0

while IFS= read -r w; do
  if [[ ! -f "$w/wrangler.toml" ]]; then
    echo "ERROR: $w is listed in deploy-map.json but has no wrangler.toml"
    FAILED=1
  fi
done <<< "$ALL_WORKERS"

exit $FAILED
```

---

## Anti-patterns

- **Deploying all Workers on every push to `main`**: eliminates the benefit of the monorepo
  structure; eight Workers deploy to fix a typo in one Worker's README.
- **Using `git diff HEAD~1` instead of `git diff origin/main...HEAD`**: `HEAD~1` only checks
  the last commit, missing changes in a squash-merge that collapsed multiple commits. Always
  diff against the merge base.
- **Not including `pnpm-lock.yaml` as an `__ALL__` trigger**: a lockfile change may alter
  the bundled output of any Worker due to transitive dependency version changes.
- **Caching the affected-workers computation**: the set of changed files must be recomputed
  from the actual `git diff` at deploy time, not cached from a PR check run that may have
  been computed on a different commit.
- **Missing `fail-fast: false` in the matrix**: if one Worker fails to deploy, the remaining
  Workers should still deploy. A single failing Worker should not block the whole monorepo.

---

## Gotchas

- **`git diff --name-only origin/main...HEAD` (three dots) vs `origin/main..HEAD` (two
  dots)**: three dots computes the diff from the merge base, which is what you want on a
  feature branch. Two dots gives you the diff including diverging `main` commits not on your
  branch, potentially inflating the affected set.
- **Wrangler rate limits**: Cloudflare's API enforces rate limits on deploys. Setting
  `max-parallel: 3` in the matrix strategy avoids HTTP 429 responses. Monitor for
  `429 Too Many Requests` in the Wrangler deploy logs.
- **Preview environments and `--env` flag**: the selective deploy workflow deploys to
  `production`. For PRs, a separate workflow deploys to named preview environments
  (`--env preview-ORCH-412`) using the same change detection logic.
- **Workers that read from other Workers via Service Bindings**: if Worker A is a Service
  Binding consumer of Worker B, and Worker B's interface changes, Worker A may need
  redeployment even if Worker A's own files did not change. Add explicit rules in
  `deploy-map.json` for these binding dependencies.
- **TypeScript build artifacts in CI**: if Workers are compiled (esbuild/tsc) before deploy,
  a change to a shared type file rebuilds all Workers but only the affected ones are deployed.
  The build step should remain broad; the deploy step is what is gated.

---

## Verification

```bash
# Test the detection script locally
bash scripts/affected-workers.sh origin/main

# Simulate a change to the search worker
git stash
echo "// test" >> workers/search/src/index.ts
bash scripts/affected-workers.sh HEAD~1
# Expected: workers/search

# Simulate a lockfile change
echo "" >> pnpm-lock.yaml
bash scripts/affected-workers.sh HEAD~1
# Expected: all workers

# Cleanup
git checkout -- workers/search/src/index.ts pnpm-lock.yaml
git stash pop
```

---

## Related

- `monorepo-workspace-cloudflare-workers.md` — pnpm workspace setup for Workers monorepos
- `monorepo-affected-builds-2026.md` — Turborepo and Nx affected-build strategies
- `github-actions-wrangler-deploy-pipeline.md` — full Wrangler deploy pipeline reference
- `ci-cache-optimization-github-actions.md` — caching pnpm and Wrangler build artifacts

---

## Sources

- Cloudflare Wrangler `deploy` command — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- Turborepo `--filter` flag — https://turbo.build/repo/docs/reference/run#--filter
- GitHub Actions matrix strategy — https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs
- `git diff --name-only` and three-dot diff notation — https://git-scm.com/docs/git-diff
- pnpm workspace documentation — https://pnpm.io/workspaces
