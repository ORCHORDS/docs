# git-submodules-vs-subtrees

**Issue:** Git submodules vs subtrees — choice
**Date:** 2026-08-09
**Status:** documented

## Symptom
You embed an external repo. Submodules? Subtrees?
You pick submodules, then forget
`submodule update` after every clone. The empty
directory strikes again. You wish you'd picked right.

## Root cause
**Submodules + forget = empty dir.** Or use subtrees.

**Source:** Atlassian + Pro Git 2026.

## The "submodules" concept

Submodules:
- **Pointer:** Commit hash
- **History:** Separate
- **Update:** `git submodule update`
- **Detached HEAD:** Default
- **Use:** Version-locked vendor

The submodule is a pointer.

## The "subtrees" pattern

For subtrees:
- **History:** Inlined
- **No special:** At clone
- **Merge strategy:** Custom
- **Use:** Transparent sharing
- **Why:** Users unaware

The subtree is inlined.

## The "decision" pattern

For choice:
- **Submodule:** Vendor, version-locked
- **Subtree:** Shared, transparent
- **Modern:** Partial clone
- **Default:** Monorepo + pkg mgr
- **Why:** Each has tradeoffs

The decision is per need.

## The "submodule update" pattern

For init:
```bash
git clone <repo>
git submodule update --init --recursive
# or
git clone --recurse-submodules <repo>
```

The update is required.

## The "subtree add" pattern

For add:
```bash
git subtree add --prefix=vendor/lib \
  https://github.com/foo/lib.git main --squash
```

The add is one command.

## The "subtree pull" pattern

For update:
```bash
git subtree pull --prefix=vendor/lib \
  https://github.com/foo/lib.git main --squash
```

The pull is per need.

## The "submodule risks" pattern

For submodule:
- **Detached HEAD:** Orphans
- **No review:** Pointer bump
- **Audit:** Often missed
- **Recovery:** Hard
- **Why:** Complex

The risk is detached.

## The "subtree risks" pattern

For subtree:
- **History:** Bloats
- **Contribute back:** Custom
- **Merge:** Confusing
- **Why:** Different model

The risk is bloat.

## The "partial clone" pattern

For modern:
```bash
git clone --filter=blob:none <repo>
git clone --filter=tree:0 <repo>
# 2026 best for large deps
```

The partial is the future.

## The "monorepo alternative" pattern

For monorepo:
- **Bazel:** Build graph
- **Nx:** Task runner
- **Turborepo:** Cache
- **Pants:** Polyglot
- **Why:** Single tree

The monorepo replaces both.

## The "no submodule update" anti-pattern

For forget:
- **Issue:** Empty dir
- **Fix:** `--recurse-submodules`

The update is required.

## The "fast-moving internal" anti-pattern

For internal:
- **Issue:** Constant churn
- **Fix:** Monorepo + package

The internal is monorepo.

## The "commit in detached" anti-pattern

For detached:
- **Issue:** Lost commits
- **Fix:** Branch first

The branch is created.

## The "no push back" anti-pattern

For subtree:
- **Issue:** Want to contribute
- **Fix:** Subtree workflow

The push back is planned.

## The "mixed commit" anti-pattern

For mixed:
- **Issue:** Boundary lost
- **Fix:** Separate commits

The boundary is kept.

## The "submodule audit gap" anti-pattern

For audit:
- **Issue:** Pointer not reviewed
- **Fix:** Review pointer SHA

The pointer is reviewed.

## The "submodule for monorepo" anti-pattern

For monorepo:
- **Issue:** Operational complexity
- **Fix:** Monorepo + package mgr

The monorepo is single.

## The "decision checklist" pattern

For choice:
- [ ] Vendor / version-locked?
- [ ] Bidirectional updates?
- [ ] Users need to know?
- [ ] CI on single tree?
- [ ] Performance critical?
- [ ] Audit needed?
- [ ] Consider partial clone
- [ ] Consider monorepo

The checklist is 8.

## The "monorepo + workspace" pattern

For monorepo:
```json
// package.json (pnpm)
{
  "workspaces": ["packages/*"]
}
```

The workspace is the answer.

## The "submodule + status" pattern

For check:
```bash
git submodule status
# Output: SHA, branch, status
```

The status is per module.

## The "submodule CI" pattern

For CI:
```yaml
- uses: actions/checkout@v4
  with:
    submodules: recursive
```

The submodule is recursive.

## The "subtree split" pattern

For split:
```bash
git subtree split \
  --prefix=vendor/lib \
  --branch=lib-upstream
```

The split is per need.

## The "vs npm" pattern

For shared:
- **npm/pnpm workspace:** Same repo
- **Submodule:** Cross-repo
- **Why:** When truly external
- **Fix:** Pkg mgr when same

The pkg mgr is in-repo.

## The "no .gitmodules" anti-pattern

For missing:
- **Issue:** Submodule not tracked
- **Fix:** Add + commit

The gitmodules is committed.

## The "submodule checklist" pattern

For submodule:
- [ ] Documented
- [ ] Update in CI
- [ ] Review pointer bumps
- [ ] Branch before commit
- [ ] Recursive in checkout
- [ ] .gitmodules committed

The checklist is 6.

## The "subtree checklist" pattern

For subtree:
- [ ] Add with --squash
- [ ] Pull periodically
- [ ] Split for push back
- [ ] Bloat aware
- [ ] Squash for cleanliness

The checklist is 5.

## Verification
- **Test:** Clone works
- **Test:** CI builds
- **Test:** Update works
- **Audit:** Per pointer bump

## Gotchas
- **The "no update" anti-pattern.** Recursive.
- **The "detached commit" anti-pattern.** Branch.
- **The "audit gap" anti-pattern.** Review.

## Related
- `worktree/git-bisect-run-2026.md`
- `worktree/cherry-pick-revert-bisect.md`
- `worktree/git-hooks-2026.md`
- `worktree/rebase-vs-merge-detail.md`
- `infra/monorepo-2026.md`
- `patterns/repository-pattern.md`
- Atlassian submodule: https://www.atlassian.com/git/tutorials/git-submodule
- Atlassian subtree: https://www.atlassian.com/git/tutorials/git-subtree
- Pro Git: https://git-scm.com/book/en/v2/Git-Tools-Submodules
