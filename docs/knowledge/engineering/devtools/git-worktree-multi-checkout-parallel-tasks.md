# Git Worktree for Parallel Tasks and Multi-Checkout Workflows

Context switching kills momentum: you are mid-feature when a production incident or an urgent review lands, and the cheapest-looking escape — `git stash`, switch branches, come back — leaves stashes orphaned, untracked files colliding, and rebuild caches invalidated. `git worktree` attaches multiple working trees to one repository, each checked out to a different branch, in separate directories. One clone, N checkouts, no stashing. This article covers the mechanics, the interaction with submodules and indexes, disk-layout practice, and the operational discipline that keeps multi-checkout workflows from decaying into directory sprawl.

## Scope

This article addresses `git worktree` usage: adding/listing/removing linked working trees, the per-worktree HEAD and index separation, branch exclusivity constraints, prune mechanics, and practical patterns (hotfix alongside feature, running two versions side by side, long-lived review checkouts, pre-tooling like build caches per tree). It does not cover submodules in depth, sparse checkouts, or remote worktrees.

## Workflow or implementation guidance

A repository normally has one working tree (the checkout directory) sharing the single `.git` directory. `git worktree add ../hotfix-2.7.4 hotfix/2.7.4` creates a second working directory whose metadata lives under `<repo>/.git/worktrees/<name>/` — each worktree gets its own `HEAD`, index, and `MERGE_HEAD` state, while objects, refs, and config remain shared. Consequences:

1. **Branch exclusivity.** A branch can be checked out in only one worktree at a time (Git refuses the second checkout to protect the per-worktree index from divergence). `git worktree add -b newbranch path/` creates and checks out a fresh branch in the new tree — the common pattern, since the current task's branch is checked out in the main tree.
2. **Shared object store.** All worktrees read/write one object database. A fetch in any tree updates refs for everyone; a build in tree A that triggers garbage collection can prune objects another tree still needs only in unreachable states (rare; reflogs protect this — but reflog expiry matters if you use aggressive GC settings).
3. **Per-tree build state.** Each worktree is a real directory with its own untracked files — `node_modules`, `target`, `.venv` — so builds in different trees don't trample each other. That is simultaneously the win (parallel versions buildable side by side) and the cost (disk and install time per tree). For heavy dependency trees, share caches where the toolchain supports it (npm/pnpm global store, Cargo target dir override, Docker layer caches).

Core patterns:

- **Interrupt-driven switching.** Feature work in tree A; incident arrives; `git worktree add ../inc-555 -b hotfix/inc-555`; fix, ship from tree B; `git worktree remove ../inc-555` once merged. Tree A never moved: editor state, uncommitted scratch, running dev server all intact.
- **Side-by-side comparison.** Check out the release branch in one tree and `main` in another to diff behavior, run both test suites against a regression, or bisect across trees. Because objects are shared, the second tree costs only working files, not a second clone's history.
- **Long-lived review/demo trees.** A `../reviews` tree kept on `main`, pulled fresh for reviewing PRs without disturbing your feature tree; a `../demo` tree pinned to the last release for reproducing customer reports against shipped code.
- **Tooling trees.** Some teams keep a dedicated tree for generated-heavy operations (docs builds, benchmark runs) whose untracked artifacts would otherwise pollute the feature tree's `git status`.

Disk and hygiene discipline:

- Keep worktrees as siblings of the main repo (`../wt-<branch>` or a `~/worktrees/<repo>/` directory) so `git worktree list` reads coherently and cleanup scripts can find them; the naming convention is yours, consistency is what matters.
- Remove trees when the task ends: `git worktree remove <path>` (refuses if dirty; `--force` overrides deliberately). If a tree was deleted by hand (`rm -rf`), run `git worktree prune` in the main tree to clear stale metadata; `git worktree list --porcelain` shows what Git still believes.
- Locked worktrees: `git worktree lock <path>` marks a tree exempt from prune operations (e.g., a tree on removable media or temporarily unmounted); unlock when done.
- Bare-clone hub pattern for many trees: `git clone --bare`, then `git worktree add` inside it for each task, so no single tree is "special" (the main-repo-is-special asymmetry disappears; the hub is never checked out directly, and `main` can live in its own tree). Teams with heavy parallelism standardize on this.

Interactions worth knowing:

- **Hooks and config are shared** (`.git/config`, hooks dir): a hook change affects all trees; a per-tree tool override must be handled by the tool (e.g., env vars set per shell), not Git.
- **`GIT_DIR`/`GIT_WORK_TREE`** environment overrides interact badly with worktrees if set globally (IDEs and shells that export them break resolution); unset them, let Git resolve per-invocation.
- **Submodules** materialize per worktree: each tree runs its own `git submodule update`, costing clone time and disk; shared clone alternatives (`--shared` submodule object stores) trade speed against fragility.
- **IDE/editor support:** open each worktree as its own project window; indexers, formatters, and language servers all key off the tree's files, which is exactly the isolation you want.

A worked example: an engineer debugging a prod-only regression keeps tree A on the feature branch with a running dev server; tree B on `release/2.7` reproduces the bug; tree C created later for bisecting (`git worktree add ../bisect` then `git bisect` inside it) leaves A and B untouched throughout. After the fix lands from B, trees B and C are removed and pruned; the only residue in the repo is new objects and refs, shared all along.

## Controls

- Adopt a worktree location/naming convention (`../wt-<task>` or `~/worktrees/<repo>/<branch>`); document it in the team README so cleanup tooling and humans agree.
- Run `git worktree list` in a weekly or pre-release hygiene pass; remove trees whose branches are merged (`git branch --merged` cross-referenced) — stale trees accumulate disk and mental load.
- After any manual `rm -rf` of a tree, run `git worktree prune` in the main tree; make this part of the runbook rather than folklore.
- Never check the same branch out in two trees (Git enforces it — don't defeat it with `--force` detached hacks; use `git worktree add --detach` for read-only inspection of arbitrary commits).
- For bare-hub layouts, script tree creation (`mkwt <branch>`) wrapping `git worktree add` plus dependency bootstrap, so a new tree is a single command consistent across the team.

## Validation evidence

- Worktree mechanics — shared object store, per-worktree HEAD/index, branch exclusivity, `add`/`list`/`remove`/`prune`/`lock` subcommands and their flags — are specified in the official git-worktree manual page published at git-scm.com, with the underlying storage model documented in the Git internals documentation.
- The Pro Git book documents workflow applications (multiple working trees) in its branching/Git-tooling chapters.
- A reproducible verification: in a scratch clone, `git worktree add ../wt2 -b experiment`; commit in wt2; return to the main tree and confirm the commit is visible (`git log experiment`) with no new clone cost; then attempt `git worktree add ../wt3 experiment` and observe Git's refusal — the exclusivity rule working as documented.

## Failure modes and correction

- **Tree sprawl.** Symptom: `git worktree list` shows a dozen stale trees; disk fills. Correct by the weekly hygiene pass and remove-on-merge discipline.
- **Prune-desync after rm -rf.** Symptom: `git worktree list` lists deleted directories; commands warn. Correct by `git worktree prune` in the main tree.
- **Shared-cache build corruption.** Symptom: builds flake when two trees share a tool cache that assumes one root. Correct by per-tree caches for unsafe tools, global stores only for tools designed for it (pnpm, cargo).
- **GIT_DIR/GIT_WORK_TREE leakage.** Symptom: Git commands in one tree touch another; IDE misbehaves. Correct by unsetting the env overrides and per-shell configuration.
- **Forced dual checkout corruption.** Symptom: index confusion after defeating exclusivity. Correct by never bypassing; use `--detach` for inspection instead.

## Limitations

- Disk cost scales with trees (working files and dependency caches per tree); sparse/partial clone mitigates history size, not working-file duplication.
- Submodule-heavy repos multiply setup cost per tree.
- Tooling that assumes a single checkout per clone (some linters, license scanners, CI scripts) needs per-tree invocation adjustments.
- Worktrees live on one machine; they do not sync or remote — the parallelism is local by design.

## Canonical sources

- Software Freedom Conservancy (Git project), git-worktree(1) Manual Page: https://git-scm.com/docs/git-worktree
- Software Freedom Conservancy (Git project), Pro Git Book (branching workflows and Git tooling): https://git-scm.com/book/en/v2
