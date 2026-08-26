# Git worktree guessRemote ambiguity controls

**Issue:** Automatically choosing an upstream by branch name can bind a new worktree to the wrong remote when several remotes expose the same branch name.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Enable `worktree.guessRemote` only when repository remote naming is governed and ambiguity is expected to fail safely. Before `git worktree add <path> <name>`, enumerate matching remote-tracking branches, reject multiple matches, and require an explicit start point for release, security, or deployment branches. After creation, verify both the checked-out commit and configured upstream. Do not infer trust from a remote name; validate its URL and fetch policy separately.

Automation should log the selected ref and object ID, use `--track` or `--no-track` deliberately, and avoid interactive fallback. A branch existing locally is a separate case from a unique remote-tracking match.

## Verification

Create two remotes with the same branch name and prove automation refuses ambiguity. Then test one unique match, no match, a stale tracking ref, and an explicit start point. Confirm fetch pruning cannot silently change a previously approved plan between preview and creation.

## Gotchas

- Guessing falls back when no unique remote match exists.
- Remote-tracking refs may be stale until a verified fetch.
- Branch names alone do not establish repository provenance.

## Official source

- [Git worktree configuration](https://git-scm.com/docs/git-worktree#Documentation/git-worktree.txt-worktreeguessRemote)
