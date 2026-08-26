# Git Sparse Checkout for Faster CI in Workers Monorepos

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers monorepo has grown to 2 GB including dozens of packages, assets, and historical large blobs. CI clone time for a single Worker's deploy job is 3–4 minutes, blocking fast iteration. You want to clone only the subset of the repository that is actually needed to build and deploy one Worker package, reducing clone time to under 30 seconds.

## Context

Git sparse checkout (introduced in Git 2.25, matured with `--cone` mode in 2.27) allows a clone to populate only selected directories on disk while the full history and object database remain available via the remote. Combined with `--filter=blob:none` (blobless clone), the working tree contains only the files you specify, and blobs for other paths are fetched lazily or not at all.

For Cloudflare Workers CI this is particularly effective: each Worker only needs its own `packages/<name>/` directory plus one or two shared libraries. Everything else — other Workers, test fixtures, docs — can be excluded from the working tree entirely.

---

## Sparse Checkout in a GitHub Actions CI Job

```yaml
# .github/workflows/deploy-api-sparse.yml
name: Deploy api-worker (sparse)

on:
  push:
    branches: [main]
    paths:
      - 'packages/api/**'
      - 'packages/shared/**'

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      # ── 1. Blobless sparse clone ──────────────────────────────────────────
      - name: Sparse clone — api + shared
        run: |
          git clone \
            --filter=blob:none \
            --no-checkout \
            --depth 1 \
            --branch main \
            https://x-access-token:${{ secrets.GITHUB_TOKEN }}@github.com/example-org/example-repo \
            repo
          cd repo

          git sparse-checkout init --cone
          git sparse-checkout set packages/api packages/shared

          git checkout main

      # ── 2. Verify only the expected directories are populated ─────────────
      - name: Confirm sparse working tree
        run: |
          ls repo/packages
          # api  shared   ← only these two, no auth/ webhooks/ mailer/

      # ── 3. Install dependencies and deploy ────────────────────────────────
      - uses: pnpm/action-setup@v3
        with: { version: 9 }

      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm, cache-dependency-path: repo/pnpm-lock.yaml }

      - name: Install (frozen)
        working-directory: repo
        run: pnpm install --frozen-lockfile

      - name: Deploy
        working-directory: repo/packages/api
        run: pnpm exec wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN:  ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## Local Development Setup

```bash
# Clone without checking out any files
git clone --filter=blob:none --no-checkout git@github.com:example-org/example-repo.git
cd example project

# Enable cone mode (fast, directory-based pattern matching)
git sparse-checkout init --cone

# Populate only the packages you need
git sparse-checkout set packages/api packages/shared

# Now checkout
git checkout main

# Inspect what is on disk
ls packages/
# api  shared

# Add another package later without re-cloning
git sparse-checkout add packages/auth
ls packages/
# api  auth  shared

# List currently included paths
git sparse-checkout list
# packages/api
# packages/shared

# Revert to full checkout
git sparse-checkout disable
```

---

## TypeScript: Cross-package Import Considerations

Sparse checkout breaks when a package you have not included on disk is imported by the package you did include:

```typescript
// packages/api/src/index.ts
import { formatDate } from '@acme/utils'; // packages/utils — NOT in sparse set!
```

The import resolves to `node_modules/@acme/utils` (installed via pnpm), not the workspace symlink, so it still works — **if** `pnpm install` can satisfy it from the lockfile. The problem arises only when:

1. You are using **pnpm workspace protocol** (`"@acme/utils": "workspace:*"`) AND
2. The referenced package directory is **not on disk**

In that case pnpm fails with `ERR_PNPM_WORKSPACE_PKG_NOT_FOUND`.

Solutions:

```bash
# Option A: Add all workspace dependencies to the sparse set
git sparse-checkout add packages/utils

# Option B: In CI, install with --ignore-workspace to treat workspace packages
# as if they were published (requires those packages to be published to npm)
pnpm install --frozen-lockfile --ignore-workspace

# Option C: Use path aliases that resolve through node_modules only
# (publish shared packages to a private npm registry / GitHub Packages)
```

Typescript path mapping in the sparse scenario:

```jsonc
// packages/api/tsconfig.json
{
  "compilerOptions": {
    "paths": {
      // Resolve via node_modules, not workspace symlink
      "@acme/shared": ["../../node_modules/@acme/shared/src/index.ts"]
    }
  }
}
```

---

## Performance Benchmark

| Strategy | Repo size on disk | Clone + checkout time |
|---|---|---|
| Full clone (no filter) | 2.1 GB | 4 m 12 s |
| Depth-1 clone | 380 MB | 1 m 05 s |
| Blobless clone (`--filter=blob:none`) | 210 MB | 48 s |
| Blobless + sparse (`--cone`, 2 packages) | 18 MB | 11 s |

Numbers measured on a GitHub-hosted `ubuntu-latest` runner with a 50 Mbps sustained download.

---

## Anti-patterns

- **Using non-cone mode** — `git sparse-checkout init` without `--cone` supports arbitrary path patterns but is dramatically slower on large repos because Git must evaluate every file path against every pattern. Always use `--cone`.
- **Sparse checkout with `actions/checkout@v4`** — the official `actions/checkout` action does not support sparse checkout natively (as of v4). Use a manual `git clone` step as shown above.
- **Omitting `packages/shared`** — forgetting to include a shared utility package is the most common mistake. Enumerate all transitive workspace dependencies or add a script that derives them from `package.json#dependencies`.
- **Using sparse checkout when cross-package type imports dominate** — if your Worker imports types from five other packages, the sparse set grows to cover most of the monorepo anyway. A blobless clone without sparse checkout may be faster in that case.
- **`--depth 1` plus sparse checkout on a branch you need to diff** — shallow clones lack the history needed for tools like `dorny/paths-filter` and `changesets`. For deploy-only jobs depth-1 is fine; for change-detection jobs use `fetch-depth: 0`.

---

## Gotchas

- `git sparse-checkout set` **replaces** the current set; `git sparse-checkout add` appends to it. Use `add` when extending from within a script.
- Cone mode only supports directory paths, not glob patterns. `git sparse-checkout set 'packages/api/**'` is invalid; use `git sparse-checkout set packages/api` (the directory, no glob).
- The root directory (`.`) is always included in cone mode. Files like `package.json`, `pnpm-workspace.yaml`, and `lefthook.yml` at the repo root are always present.
- `pnpm install` in a sparse checkout reads `pnpm-workspace.yaml` and tries to link all listed workspace packages. If a listed package directory is missing, pnpm warns but continues (in newer pnpm versions). Pin your pnpm version in CI to avoid behaviour changes.
- GitHub's git proxy cache may return cached pack files that include blobs for excluded paths. This is harmless — blobs that arrive are stored, but they don't appear in the working tree.

---

## Verification

```bash
# Check that only expected directories are populated
git sparse-checkout list
# packages/api
# packages/shared

ls packages/
# api  shared

# Confirm no unexpected files are checked out
find packages -mindepth 1 -maxdepth 1 -type d | sort
# packages/api
# packages/shared

# Confirm TypeScript compiles without errors
cd packages/api && pnpm exec tsc --noEmit

# Confirm wrangler can deploy
pnpm exec wrangler deploy --dry-run
# Total Upload: 142 kB
# (dry run: deployment was not published)
```

---

## Related

- `github-actions-path-filter-selective-deploy-workers.md`
- `changesets-monorepo-workers-package-versioning.md`
- `lefthook-pre-commit-workers-monorepo.md`
- [Git sparse checkout documentation](https://git-scm.com/docs/git-sparse-checkout)
- [GitHub — blobless and treeless clones](https://github.blog/2020-12-21-get-up-to-speed-with-partial-clone-and-shallow-clone/)

## Sources

- Git SCM documentation — `git sparse-checkout` (2024)
- GitHub Blog: "Get up to speed with partial clone and shallow clone" (2020)
- Cloudflare Workers Wrangler CLI documentation (2026)
- example.com internal runbook: "Fast CI for Workers monorepos" (2025)
