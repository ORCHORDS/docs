# Git Monorepo Management — Sparse Checkout, Partial Clone, and Build Tools

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your monorepo has 400,000 files across 50 services. `git clone`
takes 14 minutes and consumes 5 GB of disk. A developer working on
the billing service only needs 3,000 files but must clone everything.
`git status` takes 3 seconds because Git scans every file in the
working tree. Your CI pipeline rebuilds all 50 services on every
commit even when only one service changed, turning a 5-minute build
into a 45-minute build.

## Context

Git sparse checkout (cone mode, Git 2.25+) restricts the working tree
to specified directory subtrees. Combined with partial clone
(`--filter=blob:none`), it reduces clone time from 14 minutes to 90
seconds and disk usage from 5 GB to 200 MB. Scalar (built into Git
since v2.38) bundles these optimizations with FSMonitor and background
maintenance. For build orchestration, Turborepo and Nx provide
intelligent task scheduling with caching — Turborepo suits smaller
JS/TS monorepos (5-50 packages), while Nx handles larger polyglot
setups (20-500+ packages) with distributed execution.

## Sparse checkout cone mode

```bash
# Initial setup: partial clone + sparse checkout
git clone --filter=blob:none --no-checkout \
  https://github.com/org/monorepo.git
cd monorepo
git sparse-checkout init --cone
git sparse-checkout set services/billing libs/api-client libs/shared-types
git checkout main

# Add more directories later
git sparse-checkout add services/notifications

# CI-optimized: shallow + partial + sparse
git clone --filter=blob:none --depth 1 --sparse \
  https://github.com/org/monorepo.git repo
cd repo
git sparse-checkout set services/checkout
```

```
Cone mode vs non-cone mode:

  Aspect       Cone Mode              Non-Cone Mode
  ──────────────────────────────────────────────────────
  Patterns     Directory prefixes     gitignore-style globs
  Index        Sparse index enabled   Full index scan
  Speed        Hash-based matching    10-100x slower
  Safety       Refuses to drop        Can silently remove
               uncommitted changes    tracked modified files
  Status       Recommended            Deprecated
```

## Performance numbers

```
                    Full Clone       Partial + Sparse
──────────────────────────────────────────────────────
Clone time:         ~14 minutes      ~90 seconds (6-7x faster)
Disk size:          ~5 GB            ~200 MB
File count:         ~400,000         ~3,000
git status:         ~3 seconds       <200ms (with FSMonitor)
```

## Scalar (built into Git v2.38+)

```bash
# Clone with all optimizations
scalar clone https://github.com/org/monorepo.git

# Apply optimizations to existing repo
scalar register
```

```
scalar register automatically enables:
  → Partial clone (lazy blob loading)
  → Sparse checkout (cone mode)
  → FSMonitor (core.fsmonitor true)
  → Background maintenance (git maintenance start)
  → Commit-graph (core.commitGraph true)
  → Untracked cache (core.untrackedCache true)

Microsoft's Windows repo: sparse-checkout pattern evaluation dropped
from 40 minutes to 3-4 seconds after cone mode optimization.
```

## FSMonitor and commit-graph

```bash
# FSMonitor — queries OS for file changes instead of scanning
git config core.fsmonitor true
git config core.untrackedCache true
# Reduces git status from ~3s to <200ms

# Commit-graph — speeds up log, branch --contains, merge-base
git config core.commitGraph true
git config gc.writeCommitGraph true
git commit-graph write --reachable
```

## CI/CD optimization

```yaml
# GitHub Actions path filtering
on:
  pull_request:
    paths:
      - "services/billing/**"
      - "libs/api-client/**"
      - "libs/shared-types/**"

# CI-optimized checkout
# git clone --filter=blob:none --depth 1 --sparse ...
# git sparse-checkout set services/checkout libs/payments
```

## Build tool comparison: Turborepo vs Nx

```
                    Turborepo 2.x          Nx 22
────────────────────────────────────────────────────────
Sweet spot:         5-50 packages, JS/TS   20-500+ packages, polyglot
Setup:              Low (turbo.json)       Medium (nx.json + project.json)
CI single machine:  25m 32s                21m 56s (16% faster)
CI distributed:     19m 18s (manual)       9m 20s (Nx Agents, 2x faster)
Cache hit speed:    ~50ms                  ~50ms
Remote caching:     Free (Vercel)          Nx Cloud (paid)
Affected detect:    Hash-based             Graph-based (nx affected)
Code generation:    No                     Yes (generators)
Language support:   JS/TS only             JS/TS + Java, .NET, Python, Go
License:            MIT                    MIT

Industry benchmark: 60-80% CI time reduction with caching
High cache-hit: <10% of original time

Real-world:
  Stripe: 300+ services, Bazel, CI 45min → <7min
  Mercari: self-hosted Turborepo cache, CI 30min → 2min
```

## CODEOWNERS for monorepos

```
# Broad defaults first, then narrow paths
*                                @org/platform-leads
/services/auth/                  @org/auth-team
/services/billing/               @org/billing-team
/libs/api-client/                @org/platform-leads
/infra/                          @org/sre @org/security
/apps/web/                       @team-frontend
/packages/ui/                    @team-design-system
```

## Anti-patterns

- **Using non-cone mode in 2025+** — deprecated, 10-100x slower, and
  prone to silent data loss. Always use `--cone`.
- **Skipping `git maintenance start`** — without background
  maintenance, commit-graph and pack files degrade over time, slowly
  eroding performance gains.
- **Rebuilding everything on every commit** — use path filtering in
  CI and affected-project detection (Turborepo `--filter`, Nx
  `affected`) to build only what changed.
- **Widely shared package with a large API surface** — a change to
  a shared types package triggers broad rebuilds across both
  Turborepo and Nx. Minimize shared package APIs.

## Gotchas

- **Narrowing sparse-checkout without committing** — if a path
  leaving the sparse set has uncommitted changes, cone mode refuses
  the operation but non-cone mode can silently drop modified files.
  Always `git stash -u` before narrowing.
- **On-demand fetch storms** — `git log -p` or `git blame` on files
  outside the sparse set triggers individual blob fetches from the
  server. Avoid pathspec-heavy history operations on files you have
  not checked out.
- **Server partial clone support** — GitHub and GitLab support
  partial clone. Older self-hosted GitLab/Gitea instances may not.
  Verify before migrating.
- **Turborepo task sandboxing gap** — tasks can access undeclared
  files, leading to phantom cache hits. Nx and Bazel provide stricter
  isolation.
- **Polyrepo-to-monorepo migration** — use `git filter-repo
  --to-subdirectory-filter` to preserve history. CI pipelines must
  be updated to stop assuming a single project root.

## Verification

- Sparse checkout uses cone mode (`core.sparseCheckoutCone = true`).
- Partial clone configured (`remote.origin.partialclonefilter = blob:none`).
- FSMonitor enabled for large repositories.
- CI uses path filtering to build only affected services.
- CODEOWNERS file assigns teams to specific service directories.
- Build caching (Turborepo/Nx) enabled with remote cache.

## Related

- `documentation/docs/policies/worktree/git-worktree-parallel-development.md`
- `documentation/docs/policies/worktree/git-stash-workflow-management.md`
- `documentation/docs/policies/github/composite-actions-reusable-workflows.md`

## Source URLs (verified 2026-08-16)

- Monorepo Git Techniques — https://www.gitflow.dev/blog/monorepo-git-techniques
- Bring Your Monorepo Down to Size with Sparse Checkout — https://github.blog/open-source/git/bring-your-monorepo-down-to-size-with-sparse-checkout/
- The Story of Scalar — https://github.blog/open-source/git/the-story-of-scalar/
- Turborepo vs Nx vs Bazel 2026 — https://daily.dev/blog/monorepo-turborepo-vs-nx-vs-bazel-modern-development-teams/
