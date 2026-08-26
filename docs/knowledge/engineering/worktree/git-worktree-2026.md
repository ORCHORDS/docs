# git-worktree-2026

**Issue:** A team uses AI coding agents in parallel. Two agents try to checkout the same branch; the second fails. A hotfix arrives while a feature is in progress; the developer stashes, switches, fixes, switches back, and unstashes. The stash dance takes 10 minutes per hotfix.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

`git worktree` fixes this cleanly: **one repo, many checked-out branches in separate directories**, each with its own HEAD, index, and untracked files, all sharing the same object database. The feature stays exactly where it was; the hotfix happens next door.

## Root cause

`git worktree` is the built-in mechanism for parallel branch work. Each worktree is a linked working directory that shares the same `.git` object database as the main checkout. Each worktree has its own HEAD, index, and working tree files. All worktrees share the object database, remote configuration, and packed refs.

For teams running multiple AI agents in parallel, worktree is the dominant isolation primitive. For teams doing hotfixes alongside feature work, worktree eliminates the stash dance.

## The core commands

```bash
# Add a new worktree (last path segment becomes the new branch name)
git worktree add ../hotfix                    # new branch "hotfix" from HEAD
git worktree add ../review pr-123              # checkout existing branch
git worktree add -b feat-x ../feat-x main      # new branch from main
git worktree add -d ../throwaway               # detached HEAD, no branch

git worktree list                             # --porcelain for scripts
git worktree remove ../hotfix                 # clean only; -f for dirty
git worktree prune                            # clean metadata for manually deleted dirs
git worktree lock ../usb-drive --reason "removable drive"
git worktree unlock ../usb-drive
git worktree move ../old ../new               # won't move worktrees w/ submodules
git worktree repair                           # fix links after moving the main repo
```

Short aliases make it muscle memory:

```bash
git config --global alias.wta 'worktree add'
git config --global alias.wtl 'worktree list'
git config --global alias.wtr 'worktree remove'
```

## The four core use cases

**1. Hotfix without disturbing feature work**

```bash
git worktree add ../hotfix-prod origin/main
cd ../hotfix-prod
# fix, commit, push, open PR
cd ../myrepo
git worktree remove ../hotfix-prod
```

The feature's dev server never stopped.

**2. Slow tests in parallel**

```bash
git worktree add ../ci-run branch-a
cd ../ci-run && pytest --slow &
cd -  # back to main worktree, keep coding
```

Zero interference between the test run and ongoing work.

**3. Code review without polluting your state**

```bash
git worktree add ../review-456 pr-456-branch
cd ../review-456
# run it, read code, leave comments
cd - && git worktree remove ../review-456
```

**4. Multiple AI agents in parallel** (the most underrated 2025-2026 use case)

```bash
git worktree add ../agent-a -b feat-a
git worktree add ../agent-b -b feat-b
git worktree add ../agent-c -b feat-c
# three tmux panes / three terminal windows, one claude each
```

One branch per worktree. Three agents, three features, three dev server ports, three `node_modules` — no collisions.

## The Git version history (2024-2026)

- **Git 2.44 (Feb 2024):** `git worktree add --orphan` — creates a worktree with an unborn branch. Handy for `gh-pages`-style split deploy branches.
- **Git 2.46 (Jul 2024):** `worktree.useRelativePaths` config + `--relative-paths` flag — internal links use relative paths. The main repo (or the whole dir tree) can move without breaking worktrees.
- **Git 2.48 (Jan 2025):** `git worktree repair` auto-fixes absolute/relative path mismatches.

For teams on Git 2.44+ (most 2026 systems), the `repair` and `--relative-paths` features mean the worktree directory can move without breaking links.

## The gotchas

**You can't check out the same branch in two worktrees.** By design — prevents index divergence. Override with `--force` or use a detached HEAD.

**Submodules are painful.** `worktree move` refuses; `remove` needs `--force`. `.git/modules/` is shared, so switching submodule commits in one worktree affects the others. Heavy-submodule repos need care.

**`.env` doesn't get copied.** Use direnv — drop a `.envrc` in each worktree and it auto-loads on cd.

**Hooks are shared** (`.git/hooks/` is in the common dir). If a hook assumes repo root via a hardcoded path, it breaks in linked worktrees. Always use `git rev-parse --show-toplevel` for the current worktree's root.

**`.git` in a linked worktree is a file, not a directory.** Contents are `gitdir: /path/to/main/.git/worktrees/<name>`. Tools that read `.git/` as a directory will break.

## The disk-share trick

`node_modules` and other build artifacts are duplicated per worktree by default. Mitigations:

- **pnpm's content-addressable store** — reinstalling across worktrees uses almost no extra space
- **Rust: `CARGO_TARGET_DIR=~/.cache/cargo-target`** — shares target dirs
- **uv, poetry caches** — shareable
- **Symlinks:** `ln -s ../main-repo/node_modules ../worktree-a/node_modules` (fragile, but cheap)

For a team running 5 parallel worktrees with 200MB of `node_modules` each, the disk-share trick saves 800MB. Worth it on SSD-constrained laptops.

## The four integration strategies for parallel work

When multiple worktrees need to integrate their work into main:

**Strategy 1 — Sequential integration (safest).** Merge one worktree at a time, fix conflicts before merging the next:

```bash
git checkout main
git merge --no-ff worktree-feature-a
git merge --no-ff worktree-feature-b
git merge --no-ff worktree-feature-c
```

**Strategy 2 — Rebase before PR (most common).** Each worktree rebases onto main before opening a PR:

```bash
cd ../project-feature-a
git fetch origin
git rebase origin/main
gh pr create
```

This keeps a linear history and minimizes merge headaches.

**Strategy 3 — Pre-merge conflict detection.** Use `git merge-tree` to detect conflicts between worktree pairs before agents finish:

```bash
git merge-tree $(git merge-base A B) A B
```

If conflicts are detected, reassign or re-scope the work.

**Strategy 4 — Cherry-pick selection.** In ensemble patterns (multiple agents solving the same problem), cherry-pick the best commits from each:

```bash
git checkout main
git cherry-pick <commit-from-agent-a>
```

## The cleanup pattern

- Remove worktrees immediately after merge (don't let stale worktrees accumulate)
- Run `git worktree prune` in CI post-merge hooks
- Alert if worktree count exceeds threshold (e.g., 10)

```bash
# .gitignore (in main worktree)
.claude/worktrees/
```

## The fzf quick-switch

```bash
wtcd() { cd "$(git worktree list --porcelain | awk '/^worktree /{print $2}' | fzf)"; }
```

Type `wtcd`, fuzzy-search worktree paths, enter to `cd`.

## Verification

The tell that worktree is working:

- A team routinely runs 3-5 worktrees per developer (feature, hotfix, agent-a, agent-b, review)
- Stash usage has dropped to near zero
- Hotfixes happen without "save your work" interruptions
- The `git worktree list` output is familiar to every developer
- AI agents run in parallel without checkout collisions

The tell it isn't:

- A team does the stash-switch-unstash dance for every hotfix
- Two AI agents cannot run simultaneously on the same repo
- "WIP" commits litter the history (a workaround for not being able to switch)
- Long-running tests block feature work

## Gotchas

- **Same branch can't be checked out twice.** Use `--force` for detached HEAD or pick a different branch.
- **Submodules + worktree is fragile.** Test before relying on it; have a backup plan.
- **`.env` doesn't get copied.** Use direnv.
- **Hooks assume repo root.** Use `git rev-parse --show-toplevel`, not hardcoded paths.
- **Build artifacts duplicate by default.** Use pnpm, `CARGO_TARGET_DIR`, or symlinks.
- **Stale worktrees accumulate.** `git worktree prune` regularly; set a count threshold.
- **AI agents in parallel is the killer 2026 use case.** Worktree is required, not optional.

## Related

- `worktree/git-rerere.md` — replaying conflict resolutions across worktrees
- `worktree/git-bisect-automation.md` — finding regressions in shared history
- `worktree/husky-lint-staged.md` — hooks shared across worktrees

## Source URLs (verified 2026-08-10)

- https://recca0120.github.io/en/2026/04/14/git-worktree-parallel-work/
- https://zylos.ai/research/2026-02-22-git-worktree-parallel-ai-development/
- https://andrewlock.net/working-on-two-git-branches-at-once-with-git-worktree/
- https://git-scm.com/docs/git-worktree
- https://blog.itdepends.be/parallel-workflows-git-worktrees-agents/
