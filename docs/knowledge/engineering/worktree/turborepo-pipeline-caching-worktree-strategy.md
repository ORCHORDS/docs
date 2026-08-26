# Turborepo Pipeline Caching with Git Worktree Isolation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You provision two worktrees from the same repository — one for a long-running feature
branch, one as a hotfix — and run `turbo build` in both. Turborepo's default cache key
is content-hash-based and can produce false cache hits: the hotfix worktree fetches a
cached build artefact from the feature branch because a shared package hasn't changed,
even though a Workers binding differs between environments. You need the cache to remain
correct across worktrees while still sharing hits for genuinely unchanged packages.

## Context

Turborepo derives its cache key from input file hashes, declared `env` vars, and task
configuration. It does **not** intrinsically know about git worktrees. Two worktrees that
share a pnpm store and differ only in branch-specific files can produce identical input
hashes for packages that weren't modified on either branch. Adding worktree-discriminating
signals — branch name, worktree path, or a sentinel env var — into Turbo's cache key
prevents cross-branch pollution while preserving hits within a single worktree session.

---

## 1. Adding a Worktree Discriminator to turbo.json

```jsonc
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "outputs": [".next/**", "dist/**", ".wrangler/dist/**"],
      "env": [
        "NODE_ENV",
        "TURBO_TEAM",
        "BRANCH_SLUG"         // <-- worktree discriminator
      ]
    },
    "test": {
      "outputs": ["coverage/**"],
      "env": ["NODE_ENV", "BRANCH_SLUG"]
    },
    "deploy": {
      "dependsOn": ["^build"],
      "outputs": [],
      "env": ["CLOUDFLARE_API_TOKEN", "WRANGLER_ENV", "BRANCH_SLUG"]
    }
  }
}
```

`BRANCH_SLUG` is set once per worktree session and flows into every cache key that
declares it. Packages unchanged between branches still hit the cache as long as
`BRANCH_SLUG` matches (i.e., within the same worktree session).

## 2. Setting BRANCH_SLUG Per Worktree

```bash
# scripts/worktree-env.sh — source this after cd-ing into a worktree
set -euo pipefail

BRANCH=$(git branch --show-current 2>/dev/null || echo "detached-$(git rev-parse --short HEAD)")
# Slugify: lowercase, replace non-alphanum with dash, trim trailing dashes
export BRANCH_SLUG=$(echo "$BRANCH" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/-\+$//')

echo "BRANCH_SLUG=$BRANCH_SLUG"
```

```bash
# In each worktree terminal:
source /repo/../wt-feature-auth/scripts/worktree-env.sh
# => BRANCH_SLUG=feature-auth-jwt-refresh

pnpm turbo build
```

For CI, inject `BRANCH_SLUG` from the GitHub Actions context:

```yaml
# .github/workflows/ci.yml
- name: Set branch slug
  run: |
    SLUG=$(echo "${{ github.head_ref || github.ref_name }}" \
      | tr '[:upper:]' '[:lower:]' \
      | sed 's/[^a-z0-9]/-/g' \
      | sed 's/-\+$//')
    echo "BRANCH_SLUG=$SLUG" >> "$GITHUB_ENV"
```

## 3. Remote Cache with Branch-Scoped Team Tokens

```bash
# packages/db/.turbo/config.json  (per-worktree override — gitignored)
{
  "teamId": "team_repo_prod",
  "apiUrl": "https://api.turbo.build"
}
```

```bash
# For a feature worktree, override the team to a branch-scoped token
export TURBO_TOKEN="${FEATURE_BRANCH_TURBO_TOKEN}"
export TURBO_TEAM="team_repo_feature"
```

Branch-scoped team tokens are available in Vercel's remote cache. Using separate teams
for main vs. feature branches ensures main's cache is never polluted by a partially-built
feature artefact that happens to share the same hash.

## 4. Input Glob Overrides for Wrangler Artefacts

```jsonc
// turbo.json — explicit inputs prevent stale hits when wrangler.jsonc changes
{
  "tasks": {
    "build": {
      "inputs": [
        "src/**",
        "wrangler.jsonc",          // bindings change = new cache key
        "../../packages/db/src/**" // cross-package dep, explicit
      ],
      "outputs": [".wrangler/dist/**"]
    }
  }
}
```

Without explicit `inputs`, Turbo hashes all tracked files in the package directory.
Adding `wrangler.jsonc` ensures a binding change (e.g., a new D1 database ID) busts
the cache even if no TypeScript source changed.

## 5. Verifying Cache Hits and Misses Across Worktrees

```typescript
// scripts/verify-cache-isolation.ts
import { execSync } from "node:child_process";

interface WorktreeVerification {
  path: string;
  branchSlug: string;
  expectedCacheStatus: "HIT" | "MISS";
}

const cases: WorktreeVerification[] = [
  { path: "../wt-main",         branchSlug: "main",                expectedCacheStatus: "HIT"  },
  { path: "../wt-feature-auth", branchSlug: "feature-auth-jwt",    expectedCacheStatus: "MISS" },
];

for (const { path, branchSlug, expectedCacheStatus } of cases) {
  const output = execSync(
    `BRANCH_SLUG=${branchSlug} pnpm turbo build --dry=json`,
    { cwd: path, encoding: "utf8" }
  );

  const result = JSON.parse(output) as { tasks: Array<{ cache: { status: string } }> };
  const statuses = result.tasks.map((t) => t.cache.status);
  const allMatch = statuses.every((s) => s === expectedCacheStatus);

  console.log(`${path}: expected=${expectedCacheStatus}, got=${statuses.join(",")} — ${allMatch ? "OK" : "FAIL"}`);
}
```

## 6. Pruned Worktree Builds with turbo prune

```bash
# Create a pruned subgraph for the api package only (useful for Docker-style worktrees)
pnpm turbo prune @repo/api --out-dir ./pruned-api

# Move the pruned output into a dedicated worktree directory
# (worktree must already exist at the target path)
cp -r ./pruned-api/* ../wt-api-hotfix/
```

`turbo prune` produces a minimal monorepo with only the transitive deps of the target
package, reducing the scope of cache keys and install surface in worktrees used for
single-package hotfixes.

---

## Anti-patterns

- **Relying solely on content hashes across worktrees** — two branches that haven't
  touched shared packages will share cache entries, causing build artefacts from one
  branch to serve another silently.
- **Setting `BRANCH_SLUG` globally in `~/.bashrc`** — it won't update when you switch
  worktrees, leading to stale discriminators.
- **Using `TURBO_FORCE=true` as a workaround** — bypasses caching entirely rather than
  fixing the isolation boundary; defeats remote cache ROI.
- **Omitting `wrangler.jsonc` from `inputs`** — binding changes don't bust the cache,
  so Workers deploys can carry wrong binding metadata from a cached build.

## Gotchas

- `BRANCH_SLUG` must be declared in `turbo.json`'s `env` array to affect the cache key.
  Setting the env var alone without declaring it in the task has no effect.
- Turbo's `--dry=json` output schema changed between Turbo v1 and v2. The field path
  is `task.cache.status` in v2 vs `task.cacheState.cacheStatus` in v1.
- Remote cache hits are validated by the team's token. If `TURBO_TOKEN` rotates mid-
  worktree session, previously recorded hits become unvalidatable — Turbo falls back to
  a full rebuild silently.
- `turbo prune` does not copy `.git` or `node_modules`. After pruning, run
  `pnpm install --frozen-lockfile` in the pruned directory before building.

## Verification

```bash
# First run — expect all MISS
BRANCH_SLUG=feature-auth pnpm turbo build 2>&1 | grep "cache"
# => FULL TURBO — 0 cached, 5 total

# Second run same branch — expect all HIT
BRANCH_SLUG=feature-auth pnpm turbo build 2>&1 | grep "cache"
# => FULL TURBO — 5 cached, 5 total

# Different branch — expect MISS on changed packages, HIT on unchanged
BRANCH_SLUG=hotfix-login pnpm turbo build 2>&1 | grep "cache"
# => 2 cached, 3 total (unchanged shared packages hit; changed packages miss)
```

## Related

- `turborepo-pipeline-prune-selective-build-workers.md`
- `turborepo-remote-cache-cloudflare-r2-backend.md`
- `turborepo-task-graph-visualization-debugging.md`
- `git-worktree-lockfile-isolation.md`
- `monorepo-affected-builds-2026.md`

## Sources

- Turborepo caching docs — turbo.build/repo/docs/crafting-your-repository/caching
- Turborepo `env` inputs — turbo.build/repo/docs/reference/configuration#env
- `turbo prune` reference — turbo.build/repo/docs/reference/prune
