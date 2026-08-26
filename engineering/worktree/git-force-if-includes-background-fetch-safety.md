# Git force-if-includes and background-fetch safety

**Issue:** A background fetch can advance a remote-tracking ref and weaken an unspecified `--force-with-lease` expectation, allowing a rewritten push to overwrite work the user has not actually incorporated.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

For the strongest force-push contract, capture the exact remote object ID reviewed by the user and pass it as the expected value in `--force-with-lease=<ref>:<expect>`. When using the tracking-ref form of `--force-with-lease`, add `--force-if-includes` (or governed `push.useForceIfIncludes=true`) so Git verifies that the updated remote-tracking tip is reachable from the local branch's reflog history.

Fetch immediately before review, show the remote/local range, and scope the push to one explicit ref. Keep automated background fetches from silently changing the review premise, protect shared branches server-side, and never replace these checks with plain `--force`.

## Verification

In a disposable remote, create an unseen concurrent commit, advance the local tracking ref through a background fetch, rewrite local history without incorporating the commit, and require the guarded push to fail. Then incorporate the remote tip and verify the intended push succeeds. Repeat with an explicit expected OID, stale reflog, multiple refs, and server branch protection.

## Gotchas

- `--force-if-includes` is an ancillary check for specific lease forms; it is not a general replacement for a lease.
- Reflog expiry can affect reachability evidence.
- Client checks do not replace server authorization and protected-branch policy.

## Official source

- [Git push force-with-lease and force-if-includes](https://git-scm.com/docs/git-push)
