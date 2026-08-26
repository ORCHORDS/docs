# Git Worktrees with GitHub Actions Matrix for Parallel Cloudflare Workers Deployment

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a monorepo with multiple Cloudflare Workers packages and want to deploy all of them in parallel during CI, without each job interfering with the others. Sequential deploys are slow, but naive parallel deploys can corrupt shared working-tree state. You need a clean, isolated checkout per deploy job.

## Context

GitHub Actions matrix strategy spins up independent runners for each combination, but all runners share the same repository clone path if you use a standard `actions/checkout`. Git worktrees let a single clone expose multiple branches or commits at independent filesystem paths, one per matrix leg, eliminating redundant full clones. Because each Worker package has its own `wrangler.toml`, the deploy step only needs access to its own directory subtree. Adding `concurrency: group` prevents double-deploys when two pushes land in quick succession on the same branch.

## Discovering Worker Packages

Before wiring up the matrix, enumerate packages that contain a `wrangler.toml`:

```bash
# From repo root — list all Worker package directories
find packages -name 'wrangler.toml' -maxdepth 3 | \
  sed 's|/wrangler.toml||' | sort
# packages/api-gateway
# packages/auth-worker
# packages/image-resizer
# packages/webhooks
```

Capture this list as a JSON array so the Actions matrix can consume it:

```bash
WORKERS=$(find packages -name 'wrangler.toml' -maxdepth 3 \
  | sed 's|/wrangler.toml||' \
  | jq -R . | jq -cs .)
echo "matrix={\"package\":$WORKERS}" >> "$GITHUB_OUTPUT"
```

## GitHub Actions Workflow

```yaml
# .github/workflows/deploy-workers.yml
name: Deploy Cloudflare Workers

on:
  push:
    branches: [main]

concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: false   # let in-flight deploys finish; queue next

jobs:
  discover:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.set-matrix.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4
      - id: set-matrix
        run: |
          WORKERS=$(find packages -name 'wrangler.toml' -maxdepth 3 \
            | sed 's|/wrangler.toml||' \
            | jq -R . | jq -cs .)
          echo "matrix={\"package\":$WORKERS}" >> "$GITHUB_OUTPUT"

  deploy:
    needs: discover
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.discover.outputs.matrix) }}
      fail-fast: true          # abort remaining legs on first failure
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0       # full history needed for worktree

      - name: Set up git worktree for package
        run: |
          PKG="${{ matrix.package }}"
          SLUG=$(echo "$PKG" | tr '/' '-')
          WORKTREE_PATH="/tmp/wt-${SLUG}"
          git worktree add "$WORKTREE_PATH" HEAD
          echo "WORKTREE_PATH=$WORKTREE_PATH" >> "$GITHUB_ENV"
          echo "PKG=$PKG"                     >> "$GITHUB_ENV"

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - name: Install dependencies
        working-directory: ${{ env.WORKTREE_PATH }}
        run: pnpm install --frozen-lockfile

      - name: Deploy Worker
        working-directory: ${{ env.WORKTREE_PATH }}/${{ env.PKG }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: pnpm exec wrangler deploy --env production

      - name: Collect deploy result
        if: always()
        run: |
          echo "DEPLOY_STATUS=${{ job.status }}" >> deploy-results.txt
          echo "PACKAGE=${{ matrix.package }}"  >> deploy-results.txt

      - name: Upload result artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: deploy-result-${{ strategy.job-index }}
          path: deploy-results.txt

      - name: Remove worktree
        if: always()
        run: git worktree remove --force "$WORKTREE_PATH" || true

  summarise:
    needs: deploy
    runs-on: ubuntu-latest
    if: always()
    steps:
      - uses: actions/download-artifact@v4
        with:
          pattern: deploy-result-*
          merge-multiple: true
      - run: cat deploy-results.txt
```

## Worktree Lifecycle Management

Worktrees left behind after a cancelled run accumulate and confuse subsequent runs:

```bash
# Prune stale worktree references on runner startup
git worktree prune --expire=now

# List all worktrees — spot leaked paths
git worktree list

# Force-remove a stuck worktree by path
git worktree remove --force /tmp/wt-packages-api-gateway
```

Add a self-hosted runner cleanup step if your runner pool is persistent:

```bash
# /etc/cron.d/cleanup-worktrees  (persistent self-hosted runners)
@reboot find /tmp -maxdepth 1 -name 'wt-*' -type d -exec rm -rf {} +
```

## Collecting All Deploy Results

With `fail-fast: true` the matrix aborts remaining legs on first failure, but already-running legs complete. Collect results via artifacts and parse them in the `summarise` job:

```bash
# In summarise job
PASS=$(grep -c 'DEPLOY_STATUS=success' deploy-results.txt || true)
FAIL=$(grep -c 'DEPLOY_STATUS=failure' deploy-results.txt || true)
echo "Deployed: $PASS  Failed: $FAIL"
test "$FAIL" -eq 0
```

## Anti-patterns

- **Sharing a single working directory across matrix legs** — concurrent `wrangler deploy` calls in the same directory corrupt each other's `node_modules/.cache` and `dist/` outputs.
- **Using `cancel-in-progress: true` with deploys** — cancelling mid-deploy leaves a Worker in a partially-uploaded state; use `cancel-in-progress: false` or exclude the deploy workflow from concurrency cancellation.
- **Skipping `--frozen-lockfile`** — allows lockfile drift between matrix legs if one leg mutates the file before another reads it.
- **Not pruning worktrees** — leaked worktree directories prevent `git worktree add` from reusing the same path, causing job failures on re-runs.

## Gotchas

- `git worktree add` requires `fetch-depth: 0` in `actions/checkout`; shallow clones lack the refs needed to check out a new tree.
- Each worktree shares the object store but has its own index and HEAD; environment variables set in one worktree shell session do not bleed into another.
- `concurrency: group` at workflow level applies to the entire workflow run, not individual jobs; two push events will queue, not cancel.
- `fail-fast: true` is the matrix-level default; set it explicitly so the behaviour is obvious to future maintainers.
- Artifact names must be unique per upload; use `strategy.job-index` or a slugified package name, not the raw path.

## Verification

```bash
# Dry-run wrangler to check auth before pushing to CI
CLOUDFLARE_API_TOKEN=<tok> wrangler whoami

# Confirm all Workers appear in your account
wrangler deployments list --name api-gateway
wrangler deployments list --name auth-worker

# Check that stale worktrees are absent on the runner
git worktree list | grep -v '(bare)'
```

## Related

- `turborepo-affected-package-workers-deploy-gate.md`
- `pnpm-recursive-exec-workers-monorepo-build.md`

## Sources

- GitHub Actions matrix strategy — https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs
- git-worktree documentation — https://git-scm.com/docs/git-worktree
- Wrangler deploy reference — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- GitHub Actions concurrency — https://docs.github.com/en/actions/using-jobs/using-concurrency
