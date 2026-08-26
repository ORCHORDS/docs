# git-submodules-subtrees-2026

**Issue:** A team has 3 products sharing a common library. The library is in its own repo. The team copies the library into each product. The library updates; the products don't. The team has 3 versions of the same code in production.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Git offers 2 mechanisms for including external code: submodules (pointer) and subtrees (copy). The 2026 default is the monorepo, but for polyrepo setups, the choice is submodule vs subtree.

## Root cause

The structural answer to "I want to share code between projects" is one of 3 things:

1. **Submodule** — pointer to another repo at a specific commit
2. **Subtree** — merged copy of another repo's content
3. **Monorepo** — single repo for everything

Each has a different cost model. The 2026 default is monorepo for related code, submodules for genuinely external.

## The 5 submodules vs subtrees differences

| Aspect | Submodules | Subtrees |
|---|---|---|
| Storage | pointer to commit SHA | full copy merged in |
| Clone behavior | needs `--recurse-submodules` | normal `git clone` works |
| Updates | `git submodule update --remote` | `git subtree pull` |
| History | separate repo history | merged into parent history |
| Offline access | needs `git submodule init` | always available |
| CI/CD | needs init step | no extra steps |
| Repo size | small (pointers) | larger (full copy) |

Submodules track *references*; subtrees track *content*. The choice depends on your coupling model.

## The 5 submodules use cases

1. **Large, independent projects** — pulling a 500MB dataset or 100MB model binary
2. **Independent release cycles** — the shared code has its own versioning
3. **Multiple consumers** — many repos need the same external code at specific commits
4. **Read-only consumption** — you don't push back to the shared repo
5. **Auditable pinning** — you need the exact commit SHA visible in your repo history

The 5 use cases favor submodules.

## The 5 subtrees use cases

1. **Vendored code** — you forked a library to patch it
2. **Single-clone experience** — `git clone` should give you everything
3. **CI/CD simplicity** — no submodule init step in pipelines
4. **Offline access** — no separate clone step
5. **Internal packages** — shared code within a polyrepo that you control

The 5 use cases favor subtrees.

## The submodule pattern

```bash
# Add a submodule
git submodule add https://github.com/myorg/shared-lib.git libs/shared

# Clone with submodules
git clone --recurse-submodules https://github.com/myorg/myproject.git

# Update a submodule
git submodule update --remote libs/shared
git add libs/shared
git commit -m "bump shared-lib to latest"

# Make a change in the submodule
cd libs/shared
git checkout -b feature/new-api
# ... make changes
git commit -m "add new API"
git push origin feature/new-api
# Back in parent:
cd ../..
git add libs/shared
git commit -m "bump shared-lib to feature/new-api"
```

The submodule workflow is two repos, two commits. Both must be pushed.

## The subtree pattern

```bash
# Add a subtree (vendored)
git subtree add --prefix=vendor/express https://github.com/expressjs/express.git 4.18.2 --squash

# Update from upstream
git subtree pull --prefix=vendor/express https://github.com/expressjs/express.git 4.18.2 --squash

# Make a change in the subtree
# ... edit vendor/express/lib/router/index.js
git add vendor/express
git commit -m "patch Express router for custom error handling"

# Push changes back to upstream (rare)
git subtree push --prefix=vendor/express https://github.com/myorg/express.git my-fork
```

The subtree workflow is one repo, one commit. Upstream push is the rare case.

## The 5 anti-patterns

1. **Submodule without `--recurse-submodules`.** CI clones without the code; build fails.
2. **Submodule with detached HEAD.** The submodule is on a specific commit; new clones are also detached. Confusion.
3. **Subtree without `--squash`.** Bloats history with upstream commits; the parent repo grows.
4. **Mixing submodule and subtree in the same repo.** Pick one; the tooling doesn't handle both well.
5. **Submodule as a shortcut to avoid a package manager.** If the language has a package manager (npm, pip, cargo), use it. Submodule is for code that can't be packaged.

## The 3-step decision tree

1. **Can you use a package manager?** If yes, use it. Don't submodule.
2. **Is the shared code genuinely external with its own lifecycle?** If yes, submodule.
3. **Do you need a single clone experience with vendored code?** If yes, subtree.

The 3 steps cover 90%+ of cases.

## The monorepo alternative

The 2026 default for related code: monorepo. See `worktree/monorepo-pnpm-turborepo-2026.md`.

- **Pros:** atomic cross-project commits, single CI, no sync step
- **Cons:** larger repo, needs build orchestration (Turborepo, Nx)
- **When:** 2+ related projects, frequent cross-project changes, team willing to invest

For 2+ projects that change together, monorepo beats both submodules and subtrees.

## The 4 hybrid patterns

Sometimes a hybrid is right.

1. **Subtree for vendored dependencies, package manager for libraries.** `vendor/` has subtrees; `package.json` has npm.
2. **Submodule for external, monorepo for internal.** External (OpenSSL, models) as submodule; internal teams in monorepo.
3. **Subtree for patches, submodule for clean pulls.** Fork a library, subtree the fork; pull from upstream via submodule.
4. **Mixed with clear ownership boundaries.** Subtree for "we own and patch"; submodule for "they own and we consume".

The 4 hybrids are advanced; the 2026 default is to pick one and stick with it.

## The 5 best practices

1. **Document the choice in the repo.** A `ARCHITECTURE.md` or `CONTRIBUTING.md` says "we use subtrees for X, submodules for Y."
2. **CI must work for fresh clones.** Test the CI on a fresh clone; submodules need `--recurse-submodules`.
3. **Pin submodules by commit, not branch.** A commit is immutable; a branch moves.
4. **Squash subtrees.** Without `--squash`, the parent repo bloats with upstream history.
5. **Use a package manager when possible.** npm, pip, cargo, Go modules handle 90% of "share code" use cases.

## The 2026 default

The 2026 default for new projects:

- **2+ related projects** → monorepo (pnpm + Turborepo for JS; Cargo workspace for Rust)
- **External library with own lifecycle** → package manager (npm, pip, cargo)
- **External model / dataset** → Git LFS or HuggingFace
- **Patched fork of a library** → subtree with `--squash`
- **External repo with strict version pinning** → submodule

The default is rarely submodule or subtree. The 2026 pattern is monorepo for related code, package manager for libraries.

## The 3 submodule-specific gotchas

1. **Detached HEAD in submodule.** The submodule is on a commit, not a branch. `git checkout main` is needed.
2. **Submodule commits need separate push.** Pushing the parent doesn't push the submodule.
3. **`git submodule update --remote` updates silently.** Pin and review the diff before committing the bump.

## The 3 subtree-specific gotchas

1. **`git subtree push` is slow on large history.** Squash on add; minimize merges.
2. **No way to see "this file came from subtree X" in the parent history.** The history is merged.
3. **Removing a subtree is hard.** `git subtree remove` exists but has edge cases.

## Verification

The tell that submodule/subtree choice is right:

- The repo is in one of 3 patterns (monorepo, package manager, vendor)
- If submodule: CI works on fresh clone with `--recurse-submodules`
- If subtree: `--squash` is used; history is clean
- Documentation explains the choice
- Submodule is pinned to commit, not branch

The tell it isn't:

- Submodule without `--recurse-submodules`; CI fails on fresh clone
- Subtree without `--squash`; bloated history
- 3 copies of the same library in different repos
- No documentation of why submodule/subtree

## Gotchas

- **The 2026 default is monorepo or package manager.** Submodule and subtree are specialized tools.
- **Submodule is a pointer.** A commit SHA in the parent repo references a commit in the child repo. Both must be pushed.
- **Subtree is a copy.** The shared code's history is merged into the parent's history.
- **`--recurse-submodules` is mandatory for fresh clones.** Document it; automate it in CI.
- **`--squash` is mandatory for subtree adds.** Otherwise the history bloats.

## Related

- `worktree/monorepo-pnpm-turborepo-2026.md` — the 2026 default
- `worktree/branch-strategies-2026.md` — branch patterns
- `worktree/conventional-commits-monorepo-changesets-2026.md` — monorepo versioning
- `worktree/git-lfs-2026.md` — large file storage

## Source URLs (verified 2026-08-10)

- https://git-scm.com/docs/git-submodule — git-submodule docs
- https://git-scm.com/docs/git-subtree — git-subtree docs (contrib)
- https://www.grizzlypeaksoftware.com/library/git-submodules-and-subtrees-when-to-use-each-ck193k9t
- https://slicker.me/git/submodules-vs-subtrees-vs-monorepos.html
- https://geekworkbench.com/blog/technical/git-submodules-subtrees
- https://devopsbeast.com/courses/git-internals/advanced-workflows/submodules-subtrees-monorepos
- https://www.learngit.space/chapters/enterprise/large-repository-management.html
- https://stackoverflow.com/questions/31769820/differences-between-git-submodule-and-subtree
