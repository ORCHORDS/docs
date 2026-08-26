# GitHub merge-queue required-check event coverage

**Issue:** A repository can enable a merge queue yet never receive required check results if CI only listens for pull-request or push events.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

GitHub Actions workflows that provide required checks for a merge queue must handle the `merge_group` event in addition to their normal pull-request trigger. The queued merge group has its own SHA and tests the combined state that may reach the target branch.

Keep the required check name and semantics consistent across relevant events. Do not replace merge-group validation with a stale pull-request result; the queue exists to test the candidate combined state.

## Operational controls

- Inventory every required status check and confirm its provider supports merge groups.
- Apply identical security-sensitive test and policy gates to `pull_request` and `merge_group`.
- Use the event SHA deliberately for checkout, artifacts, and result reporting.
- Bound queue build concurrency from CI capacity without skipping checks.
- Reject ambiguous status names that can be supplied by an unintended workflow.
- Test cancellation and regrouping when a queued pull request changes.

## Verification

1. Add a compatible pull request to a test queue.
2. Confirm a merge-group workflow starts for the queue SHA.
3. Make a required check fail and verify the group cannot merge.
4. Combine individually passing changes that conflict logically and confirm group tests catch the issue.
5. Inspect branch protection or ruleset configuration for exact required contexts.

## Sources

- [GitHub Docs: Managing a merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
- [GitHub Docs: Events that trigger workflows — merge_group](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#merge_group)
