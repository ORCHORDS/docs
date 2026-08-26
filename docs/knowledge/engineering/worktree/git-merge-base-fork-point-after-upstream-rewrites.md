# Git merge-base fork-point after upstream rewrites

**Issue:** After an upstream branch is force-updated, an ordinary merge base can select an older ancestor and cause a topic rebase to replay commits that previously belonged to upstream.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Use `git merge-base --fork-point <upstream> <topic>` when reflog history is available and the upstream was rewritten. Inspect the candidate, compare the topic-only commit set, create a backup ref, and use explicit `rebase --onto` boundaries. Fall back to reviewed commit selection when fork-point returns no result.

## Verification

Build a disposable history with an upstream rewrite, compare ordinary merge-base and fork-point, and verify the rebased tree plus exact intended commit list. Test behavior after reflog expiration.

## Gotchas

Fork-point relies on reflog entries and may fail after expiration, garbage collection, or in shallow/fresh clones. Never feed an empty or unreviewed result into destructive history rewriting.

## Official sources

- https://git-scm.com/docs/git-merge-base
- https://git-scm.com/docs/git-rebase
