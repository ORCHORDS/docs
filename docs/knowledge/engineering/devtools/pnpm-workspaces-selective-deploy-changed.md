# pnpm Workspaces Selective Deploy for Changed Packages

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
In a Cloudflare Workers monorepo with multiple Worker apps, running `wrangler deploy` for every package on every PR is slow, expensive (API rate limits), and dangerous. The goal is to deploy only the Worker apps whose source files — or whose transitive workspace dependencies — changed relative to the merge base.

## Context
pnpm's `--filter` flag accepts a `[<git-ref>]` change specifier that lists only packages with file changes since a given commit. Combined with `--filter-prod` to include dependents, this builds a precise deploy set: if `packages/auth` changed, every Worker that depends on it is included, but unrelated Workers are skipped. This approach requires no external tooling beyond pnpm itself and works with any CI provider that exposes a base SHA.

## Identifying Changed Packages

pnpm's filter syntax for changed packages:

```bash
# List packages changed since origin/main
pnpm --filter "...[origin/main]" ls

# List packages changed since a specific commit
pnpm --filter "...[abc1234]" ls

# List packages changed since the merge base of current branch vs main
BASE=$(git merge-base HEAD origin/main)
pnpm --filter "...[${BASE}]" ls
```

The `...` prefix means "this package and all packages that depend on it (dependents)". This is the critical piece: it propagates changes upward through the dependency graph.

Without `...`:
```bash
# Only the changed package itself — does NOT include Workers that import it
pnpm --filter "[origin/main]" ls
```

With `...` (correct for deploy):
```bash
# Changed packages PLUS all packages that (directly or transitively) depend on them
pnpm --filter "...[origin/main]" ls
```

## Workspace Structure for the Pattern

```
monorepo/
├── pnpm-workspace.yaml
├── packages/
│   ├── auth/           # shared auth library
│   │   └── package.json  { "name": "@repo/auth" }
│   └── utils/          # shared utilities
│       └── package.json  { "name": "@repo/utils" }
└── apps/
    ├── api-worker/     # depends on @repo/auth, @repo/utils
    │   └── package.json
    ├── email-worker/   # depends on @repo/utils
    │   └── package.json
    └── cron-worker/    # no shared deps
        └── package.json
```

`pnpm-workspace.yaml`:

```yaml
packages:
  - "packages/*"
  - "apps/*"
```

Worker `apps/api-worker/package.json`:

```json
{
  "name": "@repo/api-worker",
  "private": true,
  "dependencies": {
    "@repo/auth": "workspace:*",
    "@repo/utils": "workspace:*"
  },
  "scripts": {
    "deploy": "wrangler deploy",
    "build": "wrangler deploy --dry-run --outdir dist"
  }
}
```

## GitHub Actions: Selective Deploy on Push to Main

`.github/workflows/deploy.yml`:

```yaml
name: Selective Deploy

on:
  push:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      changed: ${{ steps.filter.outputs.changed }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history required for merge-base

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Find changed deployable packages
        id: filter
        run: |
          # On push to main, compare against the previous commit
          BASE="${{ github.event.before }}"
          if [ "$BASE" = "0000000000000000000000000000000000000000" ]; then
            # First push — treat all packages as changed
            CHANGED=$(pnpm ls -r --depth -1 --json | jq -r '.[].name' | tr '\n' ',')
          else
            CHANGED=$(pnpm --filter "...[${BASE}]" ls --depth -1 --json 2>/dev/null \
              | jq -r '.[].name' | tr '\n' ',')
          fi
          echo "changed=${CHANGED}" >> "$GITHUB_OUTPUT"
          echo "Changed packages: ${CHANGED}"

  deploy:
    needs: detect-changes
    runs-on: ubuntu-latest
    if: needs.detect-changes.outputs.changed != ''
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Build shared libraries first
        run: |
          BASE="${{ github.event.before }}"
          pnpm --filter "...[${BASE}]" --filter "./packages/**" build

      - name: Deploy changed Workers
        run: |
          BASE="${{ github.event.before }}"
          pnpm --filter "...[${BASE}]" --filter "./apps/**" deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

## Pull Request Preview Deploy

For PR environments, compare against the base branch:

```yaml
name: PR Preview Deploy

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Build shared libs changed in this PR
        run: |
          BASE=$(git merge-base HEAD origin/${{ github.base_ref }})
          pnpm --filter "...[${BASE}]" --filter "./packages/**" run build || true

      - name: Deploy preview Workers changed in this PR
        run: |
          BASE=$(git merge-base HEAD origin/${{ github.base_ref }})
          CHANGED=$(pnpm --filter "...[${BASE}]" --filter "./apps/**" ls \
            --depth -1 --json 2>/dev/null | jq -r '.[].name')

          if [ -z "$CHANGED" ]; then
            echo "No Worker apps changed — skipping preview deploy"
            exit 0
          fi

          echo "Deploying previews for: ${CHANGED}"

          # Deploy each changed Worker to a preview environment
          pnpm --filter "...[${BASE}]" --filter "./apps/**" exec -- \
            wrangler deploy --env preview
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

## Local Developer Workflow

```bash
# See which packages you changed vs main before pushing
git fetch origin main
pnpm --filter "...[origin/main]" ls

# Build only your changed packages + their dependents
pnpm --filter "...[origin/main]" build

# Run tests for only changed packages + dependents
pnpm --filter "...[origin/main]" test

# Dry-run deploy to verify wrangler config before pushing
pnpm --filter "...[origin/main]" --filter "./apps/**" exec -- \
  wrangler deploy --dry-run
```

## Combining with --filter for App Scoping

Layer filters to limit to just Worker apps among the changed set:

```bash
# Changed packages that also match the apps/** glob
pnpm --filter "...[origin/main]" --filter "./apps/**" ls

# Changed packages that also match a specific app name
pnpm --filter "...[origin/main]" --filter "@repo/api-worker" ls

# Exclude a specific package even if it changed
pnpm --filter "...[origin/main]" --filter "!@repo/cron-worker" ls
```

## Anti-patterns

- **Using `--filter "[origin/main]"` without the `...` prefix** — This only selects the directly-changed packages, not their dependents. A Worker that imports a changed library will not be included and will ship stale code.
- **Comparing against a fixed branch name without fetching** — `origin/main` refers to the locally-cached remote ref. Without `fetch-depth: 0` and a `git fetch`, the ref may be stale and the change set wrong.
- **Deploying `packages/**` (libraries) with `wrangler deploy`** — Libraries have no `wrangler.toml`; the deploy command will error. Always scope Worker deploys to `./apps/**`.
- **Skipping library builds before Worker deploys** — Workers that import workspace packages need the library's `dist/` to be current. Build `./packages/**` before `./apps/**` in the same pipeline step.
- **Not handling the first-push case** — When `github.event.before` is all zeros (initial push to a branch), `pnpm --filter "[0000…]"` returns no packages. Handle this as a full deploy.

## Gotchas

- pnpm `--filter` change detection relies on `git diff --name-only`; untracked files are not detected — all relevant changes must be committed.
- The `ls` subcommand outputs JSON when passed `--json` but plain text otherwise; the `--depth -1` flag is required to get a flat package list instead of a tree.
- pnpm filter expressions are evaluated against the `pnpm-workspace.yaml` graph; a package not listed there is invisible to `--filter`, even if it exists on disk.
- Circular workspace dependencies cause `pnpm --filter "..."` to hang or emit an error — run `pnpm ls --depth Infinity` to detect cycles before adopting this pattern.
- If a `wrangler.toml` in an app uses `compatibility_date` that is too old, the deploy succeeds but the Worker may behave differently from local dev. Pin `compatibility_date` in each app and enforce it in CI.

## Verification

```bash
# Commit a change to packages/auth/src/index.ts
# Then verify the change set includes api-worker (which depends on auth)
git add packages/auth/src/index.ts && git commit -m "test: touch auth"
pnpm --filter "...[HEAD~1]" ls
# Expected: @repo/auth, @repo/api-worker (NOT @repo/email-worker if it doesn't depend on auth)

# Verify email-worker is NOT in the set
pnpm --filter "...[HEAD~1]" ls | grep email-worker
# Expected: no output

# Confirm dry-run deploy works for the changed set
pnpm --filter "...[HEAD~1]" --filter "./apps/**" exec -- wrangler deploy --dry-run
```

## Related
- `wrangler-config-validation-ci.md`
- `wrangler-dev-local-d1-r2-kv.md`
- `turborepo-cloudflare-workers-pipeline.md`
- `wireit-build-orchestration-workers-monorepo.md`
- `changesets-prerelease-alpha-beta-workers-ci.md`

## Sources
- https://pnpm.io/filtering#--filter-since
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://pnpm.io/cli/recursive
