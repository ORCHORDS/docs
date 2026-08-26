# ci-first-error-union-grep

**Issue:** Adding a new value to a TypeScript union type (e.g. a new member of `PaymentStatus`) breaks CI in multiple `Record<Status, ...>` lookup tables — but CI only reports the FIRST error per run. Each fix-push cycle surfaces exactly one new error, burning 3-4 full CI iterations on what grep would have caught in one pass. Observed repeatedly on example-org/example-repo CI.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why CI makes this painful

1. **First-error-only reporting.** The type-check step halts at the first missing record key; the other five broken lookups stay invisible until the next run.
2. **Self-hosted runners add queue latency.** Each iteration costs minutes of wall-clock even when the fix is a one-liner.
3. **The errors look unrelated.** A missing record key surfaces far from the union definition, so each iteration "surprises" the author again.
4. **Union changes have fan-out by design.** Exhaustive `Record<Union, T>` maps are placed exactly to force updates — the compiler is doing its job; the workflow wasn't.

## The one-pass protocol

1. **Before pushing a union change, grep every usage:** `grep -rn "Record<TheUnion" src/` plus grep for the union name itself to catch re-exports and switch statements with exhaustiveness checks.
2. **Update ALL matched sites in the same commit** — the lookup tables, the switch defaults, any `satisfies Record<...>` assertions.
3. **Run `tsc --noEmit` locally before push** — one local run replaces 3-4 CI round-trips.
4. **If CI still fails, read the error as a map, not a surprise** — fix that site, then immediately grep for siblings of the same shape before pushing again.
5. **Consider a codemod** when the fan-out exceeds ~10 sites: a scripted insert of the new key beats ten manual edits.

## Generalized preflight protocol from later CI failures

The same rule applies beyond TypeScript unions. Repeated example-org/example-repo failures in August 2026 showed that workflow and module refactors can be green at runtime yet fail required source-contract tests because those tests encode file layout, step names, or ordering assumptions. Treat those contracts as part of the dependency graph before writing the refactor.

1. **Read policy/source-contract tests before changing the thing they inspect.** If a workflow test searches for an exact step name/order, or a source-contract test reads a specific module file, inspect and reconcile that test before committing the workflow/module move. Do not discover the assumption only after CI.
2. **Prove the failure class before editing.** Fetch the workflow run, job, failing step, and logs. A red badge is not a diagnosis. Separate application/test failures from artifact-storage quota, hosted-runner availability, review-bot quota, and other external gates.
3. **Do not weaken a required gate just to turn CI green.** Run repository-controlled lint/typecheck/tests/build/evidence generation before an externally capacity-bound retained-evidence upload when policy permits, while keeping the final required upload fail-closed. This preserves useful evidence without manufacturing a false green.
4. **Reconcile overlapping workflow branches before validation.** When several PRs modify the same CI file, combine the intended behaviors deliberately, then update all associated policy tests to the reconciled contract. Merging independent workflow snapshots in arbitrary order risks silently restoring removed network installs, redundant artifacts, or stale step ordering.
5. **Batch disjoint validation, not source ownership.** Keep source fixes isolated, but create a validation-only exact-head snapshot for compatible stacks so one self-hosted run proves the combined tree. Close that validation PR unmerged after evidence is captured.
6. **Reuse concurrent work instead of duplicating commits.** Before creating a branch or replacement stack, search current branches/PRs for the same issue and compare the exact patch. If an equivalent ORCHORDS branch already exists, use it rather than adding parallel history.
7. **When a new runtime implementation already passes, fix stale contracts instead of rewriting working code.** A test that assumes implementation text remains in `auth.ts`, for example, should follow the implementation boundary after a facade refactor while retaining the same security assertion.
8. **Stop rerunning known external-only failures without a changed precondition.** If the only remaining red step is a confirmed account-level artifact quota and no capacity/account state changed, another identical run adds queue pressure but no evidence.
9. **Reconstruct stale branches from the latest target tree; never transplant an old full tree after the base moves.** A previously validated commit tree contains every file as it existed on its old parent. Re-parenting that entire tree onto a newer `main` can silently revert unrelated changes that landed in the meantime. Instead: fetch exact current `main`; use its tree as the base; overlay only the reviewed changed blobs (or reconcile only the files whose context legitimately changed); create the new commit; then compare `main...candidate` **before moving the branch ref**. Require zero behind and an exact intended file list before starting fresh checks. Any ancestry change invalidates old exact-head CI evidence.

### Failure-taxonomy checklist before the next commit

- What exact step failed?
- Is the failure repository-controlled or external?
- Which source-contract/policy tests inspect the files or step names being changed?
- Are there sibling/overlapping PRs touching the same workflow/module?
- Can disjoint fixes share one validation-only snapshot?
- Did the previous runtime behavior already pass, making the test assumption—not the implementation—the defect?
- Will this commit produce new evidence, or only reproduce an unchanged external blocker?
- Is the candidate built from the **current target tree**, with only reviewed file/blob overlays?
- Did `compare` prove zero-behind ancestry and exactly the intended changed-file set before the ref was moved?
- If the parent/base changed, have prior CI/security results been treated as historical rather than current approval?

## Broader lesson

1. **Any exhaustive-type construct is a change amplifier** — `Record<Union, T>`, discriminated-union switches, and exhaustive `never` checks all fan out.
2. **CI is a verifier, not a finder** — using it as the first place errors appear converts compile time into wall-clock deploy cycles.
3. **Grep-before-push is the cheapest static analysis** that exists; it just has to be habitual.
4. The iteration tax is predictable: expect 3-4 CI cycles when you skip the grep, expect 1 when you don't.
5. Budget the tax consciously — on self-hosted runners with limited concurrency, wasted cycles also block other agents' jobs.
6. **Source-contract and workflow-policy tests are executable dependencies of a refactor.** Read them first, just as you would grep call sites before changing a type.
7. **A red check has no meaning until its failing step is classified.** Treat external capacity gates separately from code correctness, without weakening fail-closed evidence requirements.
8. **A Git tree is a full repository snapshot, not a patch.** Reusing an old tree on a new parent is semantically different from replaying the reviewed diff; current-base reconstruction plus an exact compare is the safe primitive for ancestry repair.

## Related

- `codex-review-merge-gate.md`
- `ci-budget-exhaustion-migration.md`
- `../testing/` category broadly
