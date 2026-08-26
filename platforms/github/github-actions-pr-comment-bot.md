# github-actions-pr-comment-bot

**Issue:** Posting automated comments on pull requests from a workflow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You want to post test results, coverage reports, or diff summaries as PR comments, and update the same comment on subsequent pushes instead of creating duplicates.

## Pattern / Solution
```yaml
jobs:
  comment:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - run: echo "Coverage: 87%" > coverage.txt
      - uses: marocchino/sticky-pull-request-comment@v2
        with:
          header: coverage-report
          message: |
            ## Coverage Report
            Coverage: 87%
```
Using `gh` CLI:
```bash
gh pr comment "$PR_NUMBER" --body "Build passed"
```
Find and update existing comment:
```bash
COMMENT_ID=$(gh api repos/:owner/:repo/issues/$PR_NUMBER/comments \
  --jq '.[] | select(.body | startswith("## Coverage")) | .id')
gh api -X PATCH "repos/:owner/:repo/issues/comments/$COMMENT_ID" \
  -f body="## Coverage updated"
```

## Gotchas
- `permissions: pull-requests: write` is mandatory; the default token lacks it.
- Workflows triggered by `pull_request` from forks run with read-only tokens — use `pull_request_target` carefully.
- The `sticky-pull-request-comment` action uses the `header` field as a unique key to find and overwrite previous comments.
- Avoid posting on every commit — gate with a condition so the comment only appears when the report changes.

## Related
- `github-actions-label-pr.md`
- `github-actions-assign-reviewers.md`
