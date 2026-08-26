# Git fetch atomic ref-update contract

**Issue:** A multi-ref fetch can update some local refs and fail on another, leaving automation to read a mixed snapshot of branches and tags.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use `git fetch --atomic` when a workflow requires all selected local ref updates to commit together or none to update. Supply explicit, reviewed refspecs; preflight namespace collisions, checked-out branch restrictions, tag policy, and permissions; and serialize other writers that modify the same refs. Read the required refs only after the fetch exits successfully.

Treat the transaction boundary precisely: it governs local ref updates made by that fetch. It does not make the remote repository atomic, roll back objects already downloaded, update the working tree or index, or combine a later merge/rebase into the same transaction. Record the before/after object IDs needed by downstream reproducibility checks.

## Verification

Create a remote with several ref updates and deliberately make one local update fail; assert every selected ref retains its pre-fetch object ID under `--atomic`. Remove the conflict and assert all refs advance. Test tags, pruning, forced updates, shallow boundaries, concurrent writers, `FETCH_HEAD` consumers, and process interruption.

## Gotchas

- Downloaded objects may remain even when ref updates fail; reachability and ref state are different.
- A successful atomic fetch can still retrieve an untrusted commit.
- Consumers must not read refs concurrently before the command reports success.

## Official source

- [Git fetch --atomic](https://git-scm.com/docs/git-fetch#Documentation/git-fetch.txt---atomic)
