# Git Shallow Clone CI Optimization

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
GitHub Actions jobs for a Cloudflare Workers monorepo take 45–90 seconds just on `actions/checkout` because the repository has years of history; most CI tasks (lint, type-check, unit test, wrangler deploy) need only the current commit tree, not full ancestry.

## Context
`--depth=N` creates a *shallow clone* — Git fetches only N commits of reachable history and marks the oldest with a "shallow boundary" that tells protocol negotiation to stop there. This is categorically different from a *partial clone* (`--filter=blob:none`), which fetches full reachability but omits object types lazily. For typical Cloudflare Workers CI (no git-describe tags, no blame tooling), a depth-1 or depth-50 shallow clone gives the best speed/utility tradeoff.

## Shallow clone fundamentals
```bash
# Minimum viable: one commit, just enough to deploy
git clone --depth 1 --no-tags \
  git@github.com:example-org/example-repo.git

# Inspect the shallow boundary
git log --oneline
# a1b2c3d (HEAD -> main, origin/main) feat: add R2 upload handler

# The parent is a "grafted" root — the repo thinks this IS the root commit
git cat-file -p HEAD | grep ^parent
# (empty — depth-1 treats HEAD as a root)

# Check if a clone is shallow
git rev-parse --is-shallow-repository
# true
```

## GitHub Actions: optimising checkout depth per job
```yaml
# .github/workflows/workers-ci.yml
name: Workers CI

on:
  push:
    branches: [main, staging]
  pull_request:

jobs:
  # Jobs that only need current state: depth 1
  lint-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1       # fastest — just the working tree
      - run: pnpm install --frozen-lockfile
      - run: pnpm run lint && pnpm run typecheck

  deploy-staging:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1
      - run: wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

  # Jobs needing recent tag for git describe: depth 50–100
  build-versioned:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 100     # enough to reach the last semver tag
          fetch-tags: true     # explicit since actions/checkout@v4.1.2
      - name: Verify git describe works
        run: git describe --tags --always --dirty

  # Jobs needing full history: bisect, changelog generation, DORA metrics
  changelog:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0       # full history
          fetch-tags: true
      - run: npx conventional-changelog-cli -p angular -i CHANGELOG.md -s
```

## Deepening a shallow clone when needed
CI steps sometimes need to reach further back than the initial depth. Avoid re-cloning:

```bash
# Deepen by 50 more commits
git fetch --deepen=50

# Deepen to a specific date
git fetch --shallow-since="2026-01-01"

# Deepen until a known commit is reachable
git fetch --shallow-exclude=v2.0.0

# Convert to a full clone (unshallow)
git fetch --unshallow
```

```yaml
# Conditional unshallow in a CI step
- name: Deepen if git describe fails
  run: |
    if ! git describe --tags --always 2>/dev/null | grep -qE '^v[0-9]'; then
      echo "No reachable tag — deepening to 200 commits"
      git fetch --deepen=200 --tags
    fi
```

## Shallow clone vs partial clone: choosing the right tool
```
┌─────────────────────┬──────────────────────────────┬────────────────────────────┐
│ Need                │ Shallow clone (--depth N)    │ Partial clone (--filter)   │
├─────────────────────┼──────────────────────────────┼────────────────────────────┤
│ Fast checkout only  │ ✅ Best option               │ ✅ Also works              │
│ git blame / log     │ ⚠️  Limited to depth N       │ ✅ Full history available  │
│ git bisect          │ ❌ Boundary breaks bisect    │ ✅ Works across full hist   │
│ git describe tags   │ ⚠️  Need fetch-tags + depth  │ ✅ Works                   │
│ Large binary assets │ ⚠️  Still fetches blobs      │ ✅ Omits blobs lazily      │
│ Monorepo, many pkgs │ ✅ + sparse checkout         │ ✅ + sparse checkout       │
│ Offline / airgap    │ ✅ Bundle-friendly           │ ❌ Lazy fetch needs remote  │
└─────────────────────┴──────────────────────────────┴────────────────────────────┘
```

## Combining shallow + sparse checkout for monorepo CI
```yaml
# Only check out the affected Worker package and shared libs
- uses: actions/checkout@v4
  with:
    fetch-depth: 1
    sparse-checkout: |
      workers/kv-cache
      packages/shared-types
      package.json
      pnpm-workspace.yaml
      pnpm-lock.yaml
    sparse-checkout-cone-mode: true
```

## Measuring the improvement
```bash
#!/usr/bin/env bash
# scripts/benchmark-clone.sh
set -euo pipefail

REPO="git@github.com:example-org/example-repo.git"
TMPDIR=$(mktemp -d)

echo "=== Full clone ==="
time git clone "$REPO" "$TMPDIR/full" 2>&1 | grep -E 'objects|Receiving|Resolving'
du -sh "$TMPDIR/full/.git"

echo "=== Shallow clone (depth 1) ==="
time git clone --depth 1 --no-tags "$REPO" "$TMPDIR/shallow" 2>&1 | grep -E 'objects|Receiving|Resolving'
du -sh "$TMPDIR/shallow/.git"

echo "=== Partial clone (blob:none) ==="
time git clone --filter=blob:none --no-checkout "$REPO" "$TMPDIR/partial" 2>&1 | grep -E 'objects|Receiving|Resolving'
du -sh "$TMPDIR/partial/.git"

rm -rf "$TMPDIR"
```

## TypeScript: guard against shallow clone in scripts that need full history
```typescript
// scripts/assert-full-history.ts
import { execSync } from "node:child_process";

export function assertFullHistory(context: string): void {
  const isShallow = execSync("git rev-parse --is-shallow-repository")
    .toString()
    .trim();
  if (isShallow === "true") {
    throw new Error(
      `${context} requires full git history. ` +
      "Run: git fetch --unshallow"
    );
  }
}

// Usage in changelog generation
assertFullHistory("Changelog generation");
```

## Anti-patterns
- Setting `fetch-depth: 0` on every job by default "to be safe" — this negates all the performance benefit and is the most common CI antipattern.
- Using `fetch-depth: 1` then calling `git log` or `git blame` later in the same job without deepening first.
- Shallow cloning in jobs that run `git bisect run` — bisect needs the full range between the known-good and known-bad commits.
- Relying on `fetch-tags: true` alone without sufficient depth — tags are fetched but `git describe` still fails if the tagged commit is beyond the shallow boundary.
- Caching `.git/` in CI with mixed shallow/full clones — the cached shallow `.git` will break jobs that subsequently need full history without explicit unshallowing.

## Gotchas
- `actions/checkout@v4` changed the default for `fetch-tags` from implicit to explicit opt-in in v4.1.2 — always set `fetch-tags: true` explicitly if your job needs tags.
- Shallow clones make `git merge-base` unreliable: if the common ancestor is beyond the shallow boundary, merge-base returns the boundary commit, not the real base.
- `git bundle` created from a shallow repo carries the shallow boundary markers — the recipient sees a grafted history that may confuse tooling.
- Some third-party CI tools (e.g., semantic-release, release-please) unconditionally check `git rev-parse --is-shallow-repository` and fail loudly with unhelpful messages; check each tool's docs before defaulting to shallow.
- `git submodule update --init` on a shallow parent clone also does a shallow fetch of submodules; this is usually fine but breaks submodule-bisect scenarios.

## Verification
```bash
# Confirm clone is shallow
git rev-parse --is-shallow-repository   # → true

# Confirm depth is as expected
git rev-list --count HEAD               # should equal --depth value for depth-N clone

# Confirm tags are reachable after deepening
git describe --tags --always            # should produce e.g. v2.3.1-4-ga1b2c3d

# Time the checkout step in GitHub Actions
# Check the "Set up job" → "Checkout" step wall clock in the Actions UI
```

## Related
- [git-monorepo-sparse-checkout-management.md](git-monorepo-sparse-checkout-management.md)
- [git-backfill-partial-clone-object-policy.md](git-backfill-partial-clone-object-policy.md)
- [ci-cache-optimization-github-actions.md](ci-cache-optimization-github-actions.md)
- [monorepo-ci-parallelization.md](monorepo-ci-parallelization.md)

## Sources
- https://git-scm.com/docs/git-clone#Documentation/git-clone.txt---depthltdepthgt
- https://github.blog/2020-12-21-get-up-to-speed-with-partial-clone-and-shallow-clone/
- https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions
