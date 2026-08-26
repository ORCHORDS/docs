# stacked-prs-workflow-2026

**Issue:** A developer builds a large feature as one 2,000-line PR. Review is slow, feedback loops are long, and merge conflicts pile up. The team needs the 2026 way to ship big work in small, reviewable slices.
**Date:** 2026-08-13
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

A feature is too big for one PR but the work is sequential — step 2 depends on step 1. Creating five independent branches means five-way merge conflicts the moment any one merges. Creating one mega-PR means reviewers skim, bugs hide, and the author waits a week for feedback. The team has no tool to express "these PRs depend on each other in this order."

## What stacked PRs are

A **stack** is a chain of branches where each branch builds on its parent:

```
main
 └── feature/auth-layer1   (PR #<number> — base: main)
      └── feature/auth-layer2 (PR #<number> — base: feature/auth-layer1)
           └── feature/auth-layer3 (PR #<number> — base: feature/auth-layer2)
```

Each PR is small and reviewed independently. When #101 merges, the tool rebases #102 and #103 onto `main` automatically. This is how large features stay reviewable without losing the sequential dependency.

## The 3 mainstream tools in 2026

| Tool | Model | Hosting | Notes |
|---|---|---|---|
| **Graphite** | Hosted CLI + web | GitHub | Most polished; free for OSS, paid for private. Strong CLI (`gt`). |
| **git-spice** | Open-source CLI | GitHub, GitLab | Free, self-hosted, no account needed. Good for air-gapped orgs. |
| **GitHub native** | `ghstack`-style / "stacked diffs" | GitHub | Limited; GitHub added basic stacking support in 2025-2026. |

## The 5-rule workflow

1. **Create a base branch** off `main` for the feature: `gt create feature-auth-part1`.
2. **Commit in small logical slices** — each commit is a reviewable unit, not a WIP dump.
3. **Submit the stack** (`gt submit`) — the tool opens one PR per commit, wired with the right base.
4. **Review bottom-up** — reviewers start at the root PR and work up the stack.
5. **Merge bottom-up** — when #101 merges, the tool restacks #102/#103 onto `main`. No manual rebase.

## When to use stacks (and when not)

**Use stacks when:**
- A feature is genuinely sequential (refactor → add API → add UI → wire up).
- Your team values small PRs but the work can't be parallelized.
- You do trunk-based development and need to land work incrementally.

**Do NOT use stacks when:**
- The work is parallelizable — just use independent branches.
- Your team does long-lived feature branches and one big PR anyway (fix the process first).
- Reviewers refuse to review a PR whose base is another PR (cultural blocker, see Gotchas).

## Gotchas

- **Reviewer pushback**: some reviewers refuse to review a PR with a non-`main` base. Educate them — the tool diffs the PR against its actual parent, not `main`. The code shown is only this layer's changes.
- **Merge order matters**: always merge the root first. Merging out-of-order causes the tool to restack, which can confuse reviewers who see "new commits" that are just rebases. Annotate restacks or re-request review explicitly.
- **Force-push churn**: restacking rewrites history on child branches. Reviewers who pulled the branch locally get conflicts. Convention: review on the web UI, don't pull stacks locally.
- **Conflict at the root cascades**: if #101 conflicts on merge, the whole stack needs restacking. Resolve at the root, then `gt restack` the children. Don't try to fix conflicts in child branches individually.
- **Tool lock-in**: Graphite stores metadata. Migrating off it (or git-spice) means manually rewriting PR bases. Pick a tool you can live with for a year+.
- **CI on every layer is expensive**: each PR in the stack triggers CI. Use path-based CI filtering or mark upper layers as `draft` until the base merges to avoid burning CI minutes.

## Related
- `pr-size-guidelines.md`
- `trunk-based-development-2026.md`
- `rebase-vs-merge-detail.md`
- `draft-pr-readiness-gated-review-2026.md`
