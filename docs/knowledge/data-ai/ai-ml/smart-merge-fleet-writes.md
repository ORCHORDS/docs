# smart-merge-fleet-writes

**Issue:** Multiple agents editing the same files across parallel issue branches produce full-file overwrites: agent B's write clobbers agent A's change because each edit was "write the whole file from my context". Line-level differences get lost silently. Built as `smartMerge` for the example project fleet after watching parallel workers stomp each other.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why naive agent writes clobber

1. **Write-from-context re-serializes the entire file** — the agent's mental copy (possibly stale, possibly truncated) becomes the new truth wholesale.
2. **Parallel branches diverge invisibly** — agent A and B both started from main; neither sees the other's edits until merge, where last-writer wins.
3. **Context truncation corrupts silently** — a long file summarized out of the agent's window gets "reconstructed" on write, losing middle sections.
4. **The diff LOOKS fine** — the overwrite is often semantically plausible, so review passes until a missing function surfaces at runtime.
5. **One file, many concerns** — the more a file contains, the more likely two agents touch it and the worse the clobber.

## The smartMerge discipline

1. **Read-before-write, always against the CURRENT tree** — fetch the file fresh at edit time; never write from remembered content.
2. **Prefer minimal-diff edits (string replacement at exact anchors)** over whole-file writes — an edit that names its old-string cannot silently drop unrelated sections.
3. **Line-level merge on branch integration** — three-way merge against the common ancestor so non-overlapping hunks from both agents survive.
4. **Scope guard per agent** — an explicit file allowlist per issue/branch; two agents on disjoint files cannot clobber each other at all.
5. **Diff-size review gate** — flag any agent PR whose diff touches lines it never referenced in its reasoning; wholesale rewrites of unreferenced regions are the clobber signature.

## Fleet architecture consequences

1. **Assign issues to disjoint file sets** where possible — prevention by partitioning beats any merge algorithm.
2. **Shared files (config, index barrels) get a single owner** per campaign or serialized access via the issue queue.
3. **Checkpoint after each verified edit** — recovery from a bad merge is only as good as the last known-good state.
4. **Tests are the clobber detector** — a silently dropped change fails its test on the merged branch even when the diff hid it.
5. **Never blame the model for the architecture** — full-file writes are a tooling choice; give agents anchor-edit primitives and the failure class disappears.

## Related

- `../issues/verify-live-file-before-work.md`
- `../patterns/` review-gate patterns
