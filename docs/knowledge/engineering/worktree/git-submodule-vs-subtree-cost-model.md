# A Quantified Cost Model for Choosing Submodules Over Subtrees

## Scope

This article covers the decision between Git submodules and Git subtrees as a cost model with measurable terms: clone and fetch overhead, per-developer daily tax, upgrade ceremony, CI complexity, and repository growth, so the choice is justified by numbers a team can audit rather than by preference. It applies to vendoring shared libraries, embedding platform scaffolds, and mono-repo hybrid layouts. It does not cover package-manager workspaces (npm/pnpm packages are usually the right answer first), sparse checkout, or partial clone, which solve different problems.

## Workflow or implementation guidance

Both mechanisms inline external code into a parent repository; they invoice the team in different currencies. Submodules bill in *daily attention*: every clone, pull, and switch can require awareness of the pointer. Subtrees bill in *bulk*: bytes and merge ceremony concentrated at upgrade time, invisible day to day. The cost model makes each term explicit.

**Term 1 — Onboarding cost.** Submodule clone requires either `--recurse-submodules` at clone time or `git submodule update --init --recursive` after a plain clone; a fresh clone that skips this has empty directories and a broken build, and the failure surfaces as a confusing compile error rather than a helpful message. Subtree clone needs nothing — the content is ordinary repository data. Measure it directly: `git clone` the parent both ways (submodules configured vs converted to subtree) and time `git submodule update --init --recursive` separately. For a candidate dependency of size S, subtree adds roughly S of pack data to every clone forever; submodule adds a second fetch of S but only for developers and CI jobs that actually need it.

**Term 2 — CI cost.** CI checkouts must pass `submodules: recursive` to the checkout action (and decide whether to authenticate for private submodules — a pipeline secret question the subtree approach never raises). Count CI jobs: every matrix cell pays the submodule init. Subtree jobs check out one repository with no special flags, no recursive step, and no credential plumbing for the secondary remote.

**Term 3 — Upgrade ceremony.** Submodule upgrade is `git submodule update --remote` (or checkout of the target SHA in the submodule, then `git add <path>` in the parent), producing a one-line diff in the parent: the pointer moves. The review is trivially readable, and reverting is reverting one line. Subtree upgrade is `git subtree pull --prefix=<path> <remote> <ref>`, which merges the entire upstream delta into the parent's history; the diff is large, the merge can conflict, and if upstream rewrites or the prefix drifts, the next pull degrades. Historical introspection also splits: `git log -- <submodule-path>` shows only pointer bumps, so blame answers nothing about the vendored code — you must `cd` into the submodule for real history. Subtree history is monolithic and greppable.

**Term 4 — Contribution flow-back.** If the team expects to push changes upstream, submodules give you a working repository at the path: branch, commit, push to your fork. Subtree flow-back uses `git subtree push --prefix=<path>` which replays history and is notoriously slow on large histories; in practice teams patch upstream separately and re-vendor. When flow-back matters, weight it heavily — it is the term most often discovered late.

**Term 5 — Repository growth.** Subtree inlines objects permanently; each vendored upgrade adds another snapshot of every changed file to the parent's object store, and the parent's clone size trends upward with upstream's churn. Submodule keeps the parent tiny. For a vendor target with heavy binary assets, subtree growth can dominate every other term; for a small source-only library, it may be negligible. Measure with `git count-objects -vH` before and after a trial subtree add.

**Running the model.** For each candidate dependency, score the terms against team reality:

- Many contributors, rarely-updated vendor code, upstream maintained elsewhere: submodules' daily tax is the cost driver; if the team tolerates `update --init --recursive` in bootstrap and CI, submodules win on review granularity and repo size.
- Few contributors, frequently-rebased shared code, everyone needs it building on plain clone: subtree's zero-daily-tax wins; accept upgrade-day merge ceremony and object growth.
- Expected flow-back contributions, private upstream, or binary-heavy content: submodules, decisively — subtree push cost and growth make it the wrong tool.

A useful tiebreaker experiment: vendor the same dependency both ways in two scratch repos, run your real CI matrix against both, and record clone time, checkout size (`git count-objects -vH`), and one upgrade each way. Thirty minutes of measurement replaces weeks of arguing.

**The hybrid that usually wins for code libraries.** Before either mechanism, check whether the dependency can be consumed as a normal package. A private registry or workspace package has neither the pointer tax nor the inline growth, and versioning rides the lockfile. Reach for submodules when you must pin exact source you cannot package; reach for subtree when you must fork-and-carry content with no upstream rhythm.

## Controls

- Every submodule or subtree adoption records the scored cost model in the pull request that adds it — the terms above with measured numbers, not adjectives.
- Submodule parents commit `.gitmodules` with the exact URL and a branch pinning policy; `git config submodule.<name>.update` defaults are documented.
- CI for submodule parents uses `submodules: recursive` in checkout and fails fast if `.gitmodules` references an unreachable remote.
- Subtree prefixes are recorded once (in README or a bootstrap constant) and never renamed; prefix drift is treated as a breaking change requiring a migration note.
- Upgrade PRs for submodules show exactly the pointer diff plus changelog link; anything larger indicates the wrong mechanism was used.
- A quarterly check compares parent repo size (`git count-objects -vH`) against the subtree growth estimate from the adoption PR; divergence triggers re-evaluation.

## Validation evidence

- Fresh-clone test: clone the parent with and without `--recurse-submodules`, then attempt the project's build in both; the plain clone fails with the documented error, proving the bootstrap instruction in README is necessary and correct.
- CI reproducibility: a matrix job that deliberately omits the submodule init fails, and adding `submodules: recursive` turns it green — evidence the checkout configuration is load-bearing.
- Pointer-only upgrade: an upgrade PR's diff shows one line per submodule in `.gitmodules`-tracked pointer files and `git diff --submodule=log` renders the upstream range; any file-level noise means someone bypassed the model.
- Subtree trial numbers: `git count-objects -vH` output before and after `git subtree add`, plus timed `git clone`, captured in the adoption PR.
- Flow-back drill for submodules: make a trivial commit in the submodule, push to a fork branch, open the upstream PR — validates credentials and remotes before a real change depends on them.
- `git submodule status` runs clean (no `-` prefix entries) on every developer machine per bootstrap; CI runs the same command as a canary for broken pointers.

## Failure modes and correction

- **Detached-HEAD confusion.** Developers enter the submodule, find themselves on a detached HEAD (normal for `submodule update`), and commit into nothing. Correction: bootstrap instructs `git submodule update --init --remote` or explicit branch checkout before work; a pre-push hook in the parent can refuse when the submodule has commits on no branch.
- **Pointer moved without content.** Parent pushes a new pointer SHA, but the submodule remote never received that commit — every other clone fails `submodule update` with an unresolvable object. Correction: policy that submodule pushes precede parent pushes; CI detects by initing submodules at the exact pointer.
- **Subtree prefix drift.** A re-vendor uses a slightly different prefix; two copies coexist and both build. Correction: single-source the prefix constant; delete stale copies in the same PR that re-vendors.
- **Subtree upgrade conflicts swallowing upstream changes.** The merge resolves, but vendored behavior silently diverges from upstream. Correction: after every subtree pull, diff the prefix tree against the upstream tag tree (`git diff <upstream-tag> -- <prefix>` restructured) to surface local carry-patches explicitly.
- **Choosing by habit.** Submodules adopted because a previous team used them, with no flow-back or pinning need, taxing every clone forever. Correction: the adoption-PR cost model requirement makes the justification explicit and reviewable.
- **Binary assets via subtree.** Every upstream release doubles objects into the parent until clones crawl. Correction: size-growth term of the model fails the proposal; use a package registry or LFS-backed mechanism instead.

## Limitations

The cost model's weights are team-specific judgments; the numbers (clone time, repo size) are measurable, but their acceptable thresholds are not universal, so the model structures the decision rather than deciding it. Submodule tooling ergonomics vary across GUI clients and IDEs, and some workflows (sparse checkouts of the parent, shallow submodule clones) interact poorly with `--recursive` flags — edge cases the model abstracts away. Subtree history replay makes precise attribution of vendored changes harder for tools that assume a single project. Both mechanisms predate modern package ecosystems; for language-agnostic build tooling and supply-chain scanning, a package dependency is auditable in ways neither submodule pointers nor inlined trees are. The quarterly size check detects subtree growth only after it has happened; there is no principled forecast beyond the adoption estimate.

## Canonical sources

- Pro Git, 2nd edition — Git Tools: Submodules: https://git-scm.com/book/en/v2/Git-Tools-Submodules
- Git documentation — git-submodule (update --init --recursive, --remote): https://git-scm.com/docs/git-submodule
- Git documentation — gitsubmodules (pointer model, detached HEAD semantics): https://git-scm.com/docs/gitsubmodules
- Git documentation — git-config for subtree and submodule configuration references: https://git-scm.com/docs/git-config
