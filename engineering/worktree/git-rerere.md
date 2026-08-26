# git-rerere

**Issue:** A team rebases a long-lived feature branch onto `main` weekly. Every week, the same merge conflicts reappear in the same files. Engineers resolve them by hand every time. The same files. The same hunks. The same resolutions.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Long-lived branches hit the same conflicts on every rebase or merge. `git rerere` (reuse recorded resolution) records how a conflict was resolved once and replays the same resolution automatically on the next occurrence.

## Root cause

Git's default behavior: a conflict is a one-time decision. Every subsequent occurrence requires the same hand resolution. For branches that get rebased repeatedly (release lines, stack-of-PRs workflows, parallel feature lines), the same conflict shape can appear dozens of times during a branch's lifetime.

`rerere` solves this by recording the conflict shape (the "preimage") and your hand resolution (the "postimage") the first time you resolve a conflict, then replaying the same resolution when the same shape appears again.

## The configuration

Enable `rerere` globally and turn on auto-stage:

```bash
git config --global rerere.enabled true
git config --global rerere.autoUpdate true
```

`rerere.enabled` is the master switch. `rerere.autoUpdate` is the convenience layer: with it on, an auto-resolved file is added to the index for you, so `git status` shows it as staged rather than as an unresolved conflict you still have to `git add`.

Leave `autoUpdate` off if you prefer to eyeball every replayed resolution before staging it. This is a reasonable stance on a security-sensitive codebase.

Verify the settings are live:

```bash
git config --get rerere.enabled   # → true
git config --get rerere.autoUpdate  # → true
```

Per-repo overrides are possible by dropping `--global`. Repo-local `.git/config` wins over the global setting.

## The mechanism

When a merge or rebase hits a conflict and `rerere` is enabled, Git records two snapshots of each conflicted file:

- **Preimage** — the file with conflict markers, normalized so that incidental differences (branch names in the markers, surrounding line numbers) do not affect the fingerprint. This is what `rerere` matches against.
- **Postimage** — the resolved file after you edit it and stage the result. This is what `rerere` replays.

Both are stored under `.git/rr-cache/<hash>/`, where `<hash>` is a stable fingerprint of the normalized preimage.

The next time Git produces a conflict whose normalized preimage hashes to the same value, `rerere` looks up the cached postimage and writes it straight into your working tree. You did the thinking once; Git does the typing forever after.

The key mental model: `rerere` matches on the shape of the conflict, not on file paths, commit SHAs, or branch names.

## The first conflict — record and verify

Trigger a real conflict — for example, merging a branch that edits the same lines as `main`:

```bash
git merge feature/pricing-refactor
# Auto-merging src/pricing.js
# CONFLICT (content): Merge conflict in src/pricing.js
```

Inspect what `rerere` is tracking:

```bash
git rerere status
# → src/pricing.js
```

Resolve the conflict the way you normally would — edit the file, remove the markers, and stage it:

```bash
# Edit src/pricing.js to the correct merged content
git add src/pricing.js
```

Staging the resolved file is the moment `rerere` captures the postimage. Confirm the entry now exists in the cache:

```bash
git rerere diff  # shows preimage → your resolution for active conflicts
ls .git/rr-cache/  # one directory per recorded conflict fingerprint
```

`git rerere diff` prints a unified diff from the recorded conflict to your resolution. If it shows your intended edit, the resolution is recorded and ready to replay.

## The replay — second conflict auto-resolves

Abort and re-run the same merge (or hit the conflict again later) to see replay in action:

```bash
git merge --abort
git merge feature/pricing-refactor
# Auto-merging src/pricing.js
# CONFLICT (content): Merge conflict in src/pricing.js
# Resolved 'src/pricing.js' using previous resolution.
```

Diff the working tree against the resolution you recorded — they must be identical, and there must be no leftover conflict markers:

```bash
git diff --staged src/pricing.js  # matches your recorded resolution
grep -n '<<<<<<<\|>>>>>>>' src/pricing.js || echo "no markers — clean"
```

## The long-rebase pattern

Pair `rerere` with the long-rebase techniques:

```bash
# Rebase a long-running branch onto the updated trunk
git rebase -i origin/main
# On the first conflicting commit:
# ... resolve src/pricing.js by hand, then:
git add src/pricing.js
git rebase --continue
# On every subsequent commit that reintroduces the same conflict:
# "Resolved 'src/pricing.js' using previous resolution."
git rebase --continue  # autoUpdate already staged it
```

For a genuinely long rebase, also enable rebase auto-stash and fixup handling:

```bash
git config rebase.autoStash true   # stash a dirty tree instead of refusing to rebase
git config rebase.autoSquash true  # honour fixup!/squash! prefixes automatically
```

## The sharing pattern

The cache lives in `.git/rr-cache/` and is not pushed with your commits — `rerere` is local by default. To share resolutions across a team:

**Option A — symlink to a shared directory:**

```bash
mv .git/rr-cache .git/rr-cache.local.bak
ln -s "$HOME/shared/rr-cache" .git/rr-cache
```

**Option B — distribute specific resolutions as reviewed artifacts:**

```bash
# On the source clone: archive the vetted cache entries
tar -czf rr-cache-pricing.tgz -C .git rr-cache
# On a teammate's clone: unpack alongside the existing cache
tar -xzf rr-cache-pricing.tgz -C .git  # merges entries into .git/rr-cache/
```

## The forget pattern

If a recorded resolution is wrong, forget it:

```bash
# Re-trigger the conflict so the bad preimage is active in the working tree
git merge feature/pricing-refactor
# rerere silently replays the WRONG resolution here
# Discard the recorded resolution for this specific conflict
git rerere forget src/pricing.js
# → Updated preimage for 'src/pricing.js'
```

`git rerere forget <path>` deletes the cached entry and restores the raw conflict markers in that file. Resolve it correctly and stage it — the corrected postimage overwrites the bad one.

To wipe all recorded resolutions and start clean — for instance after a large refactor invalidates the cache — clear the whole directory:

```bash
rm -rf .git/rr-cache/*
```

## The garbage collection

`rerere` records accumulate. Default pruning:

- Unresolved conflicts older than 15 days
- Resolved conflicts older than 60 days

These are controlled via `gc.rerereUnresolved` and `gc.rerereResolved`. Adjust if your rebase cycle is longer.

## Verification

The tell that `rerere` is working:

- A long-lived feature branch hits a conflict on first rebase; you resolve it; subsequent rebases replay automatically
- `git rerere status` shows files with active conflicts; `git rerere diff` shows the recorded resolution
- A wrong resolution is corrected with `git rerere forget` and re-recorded
- Team-shared resolutions are distributed via tarball or symlink

The tell it isn't:

- The same conflict is resolved by hand on every rebase
- The cache is empty after a conflict resolution (rerere is not enabled)
- A bad resolution replays and breaks the build (autoUpdate is on but the cache wasn't verified)

## Gotchas

- **Enable `rerere.enabled` first; everything else follows.** Without it, no subcommand does recording or replay.
- **`autoUpdate` is convenience, not correctness.** Leave it off on security-sensitive codebases; you want to eyeball every replay.
- **Cache matches on conflict shape, not on files or commits.** Two different files with the same conflict shape can collide (rare but possible).
- **The cache is local; it is not pushed.** Sharing requires explicit symlink or tarball distribution.
- **`rerere forget` requires the conflict to be active.** You can't just delete a cache entry; you have to trigger the conflict first.
- **The default GC of 60 days is too short for long release lines.** Increase `gc.rerereResolved` if needed.

## Related

- `worktree/git-bisect-automation.md` — finding the commit that introduced a bug
- `worktree/release-please-semantic-release.md` — automated versioning and changelogs
- `worktree/husky-lint-staged.md` — pre-commit quality gates

## Source URLs (verified 2026-08-10)

- https://git-scm.com/book/en/v2/Git-Tools-Rerere
- https://git-scm.com/docs/git-rerere
- https://www.git-automation.com/conflict-resolution-safe-merge-operations/rerere-conflict-automation/
- https://stackoverflow.com/questions/49500943/what-is-git-rerere-and-how-does-it-work
- https://www.thisdot.co/blog/mastering-git-rerere-solving-repetitive-merge-conflicts-with-ease
