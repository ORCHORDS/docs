# GitHub Pinned-Issue Selection and Expiry

**Issue:** Pinned issues consume scarce repository attention and become misleading when resolved incidents, obsolete roadmaps, or stale notices remain at the top of the tracker.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Reserve the three available pin slots for current information that benefits most issue visitors.
- Assign each pin an owner, purpose, review date, and removal condition.
- Prefer a maintained canonical issue over duplicate announcements or transient incidents.
- Require write access for pinning automation and record why it displaced another pin.
- Unpin closed, superseded, or expired items even when their historical discussion remains valuable.

## Verification

- List pinned issues on a schedule and verify state, owner, freshness, and destination links.
- Close or supersede a test pin and confirm the review workflow removes or replaces it.
- Check that automation never exceeds platform limits or repeatedly churns pin order.

## Gotchas

- Confirm the cited feature or standard edition remains current before relying on it.
- Keep secrets, personal data, and restricted evidence out of examples and logs.
- Reassess after scope, implementation, or policy changes.

## Sources

- https://docs.github.com/en/issues/tracking-your-work-with-issues/administering-issues/pinning-an-issue-to-your-repository
