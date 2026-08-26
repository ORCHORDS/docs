# git-sparse-checkout-partial-clone

**Issue:** The monorepo clone in CI takes four minutes and 2.1 GB even though the job touches one service directory, and on developer machines `git status` has become a coffee-break. Full clones download every blob of every version of every path. Git's answers — partial clone (blobless/treeless filters) and sparse checkout (working-tree subset) — are orthogonal knobs that stack, but applying them naively in GitHub Actions backfires: on-demand fetches inside the runner can make CI slower and flakier, and pushes from filtered clones have known slowdowns. The durable setup knows which filter for which workload and how to combine them with `fetch-depth` and sparse patterns.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three knobs and what each saves

1. **Blobless clone (`--filter=blob:none`).** Downloads all commits and trees but no file contents; blobs are fetched on demand at checkout. History operations (`git log`, `git diff` between commits) mostly still work because trees/commit metadata are local — only blob content round-trips. GitHub's blog recommends blobless as the default remote-work clone.
2. **Treeless clone (`--filter=tree:0`).** Downloads only the commits on the tip; trees and blobs are fetched on demand per checkout. Fastest clone for "clone, build tip, throw away" — but nearly any extra Git command (fetch, submodule change detection) triggers tree downloads that erase the savings; least safe for interactive use.
3. **Sparse checkout (`git sparse-checkout`).** Orthogonal to filters: limits which paths are materialized in the working tree. Cone mode (`git sparse-checkout set services/api --cone`) is fast and simple; non-conce mode (`.gitignore`-style patterns in `$GIT_DIR/info/sparse-checkout`) is flexible but slower. Combine with `--filter=blob:none` so untouched directories never cost blobs.
4. **Shallow clone is a different axis.** `fetch-depth: 1` truncates history (commits), which partial clone does not — shallow breaks `git log`, blame, and anything needing parents, but pairs fine with filters for pure build jobs.
5. **What each buys in CI.** Blobless+sparse trims clone bytes to "metadata + needed paths at needed depth"; treeless trims further but only when the job does exactly one checkout and no history ops.

## Partial clone in GitHub Actions

1. **Blobless via checkout is implicit-ish, explicit is better.** `actions/checkout` fetches with a filter in some modes; for deterministic behavior do it in a `run` step: `git clone --filter=blob:none --no-checkout https://github.com/OWNER/REPO && cd REPO`. Then `git checkout` pulls only the needed blobs for the checked-out ref.
2. **Sparse checkout runs as a shell step.** First-class support in `actions/checkout` is still an open discussion (community discussion #26578), so: `git sparse-checkout init --cone && git sparse-checkout set apps/web libs/shared` before checkout. Keep the pattern list in a shared script/action so jobs can't drift.
3. **Set `fetch-depth` deliberately.** For build jobs `fetch-depth: 1`; for jobs running `git log`-based tooling (changelogs, `nx affected`, versioning) use `fetch-depth: 0` on a blobless clone — full history metadata without full blobs is the sweet spot for monorepo affected-detection (see `github-actions-monorepo-affected.md`).
4. **Beware lazy fetches inside jobs.** Any command touching unmaterialized paths (a stray `git grep` across the repo, submodule recursion, tooling that scans the tree) triggers on-demand blob/tree downloads — in CI this shows up as slow, variable step times. Prefetch hot paths explicitly: `git sparse-checkout reapply` after pattern changes; run repo-wide scans in a dedicated non-sparse job.
5. **Pushing from partial clones is a trap.** Pushes from blobless/treeless clones can be significantly slower (objects must be resolved remotely — community discussion #78325). Release/tagging jobs that push should either use a normal clone or accept and budget the cost.

## Monorepo recipe that holds up

1. **Path-filtered sparse matrix.** A dispatch job computes changed paths (`dorny/paths-filter` or `git diff --name-only`), then fans out matrix jobs each doing cone-mode sparse checkout of its service directory plus shared libs — clone time drops from minutes to seconds and scales with directory size, not repo size.
2. **Shared library pinning.** Sparse sets must include transitively-needed directories (shared `libs/`, lockfile root files like `package.json`/`pnpm-lock.yaml`, config dirs); forgetting root manifests breaks installs in ways that look like flaky CI.
3. **Concurrency + caching still apply.** Sparse clone savings don't remove the need for `concurrency: group per-PR, cancel-in-progress` and dependency caching — clone is one line item among several (see `github-actions-concurrency-groups.md`, `github-actions-monorepo-caching.md`).
4. **Developer machines: blobless + growing sparse.** Clone with `--filter=blob:none`, start sparse, widen with `git sparse-checkout add` as work moves; document the one-liner in CONTRIBUTING so onboarding clones match CI behavior.
5. **Measure clone bytes and step time before/after.** Log `du -sh .git` and job timing for a week around the change; sparse/filter configs that "feel faster" sometimes only moved cost into lazy fetches.

## Gotchas and failure modes

1. **Filter + submodules.** Fetching in treeless clones can trigger tree downloads for submodule change detection (actions/checkout issue #<number>) — disable or explicitly handle submodules in filtered jobs.
2. **Server support required.** Partial clone needs the remote to support promisor/fetch filters; GitHub.com and current GitHub Enterprise Server do, but self-hosted git servers behind firewalls may not — verify with `git rev-list --objects --filter=blob:none --all` behaving.
3. **Sparse pattern drift.** A job fails only when a refactor moves a file outside someone's stale sparse set — keep sparse patterns owned by the platform repo/script, reviewed like code, and add a CI assertion that the sparse set still contains canonical paths.
4. **`gh` CLI and some tooling assume full clones.** Tools that walk the whole tree (`gh pr checkout` on unrelated paths, linters with repo-wide defaults) can force fetches; scope them or run them in full-clone jobs.
5. **Don't persist filtered clones in caches.** Caching a `.git` directory from a filtered/sparse run and reusing it in a different-shaped job produces confusing missing-file errors — cache dependencies, not working copies.

## Related

1. **`github-actions-monorepo-strategy.md`.** Where sparse matrix fan-out sits in overall monorepo CI design.
2. **`github-actions-path-filters.md`.** Detecting changed paths that drive the sparse set.
3. **`github-actions-cache-dependencies.md`.** Complementing clone savings with dependency caching.
