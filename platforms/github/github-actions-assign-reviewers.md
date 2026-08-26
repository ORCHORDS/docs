# github-actions-assign-reviewers

**Issue:** Auto-assigning reviewers to pull requests based on code ownership or round-robin rules
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without auto-assignment, PRs sit unreviewed because no one feels responsible. CODEOWNERS handles file-based ownership; this covers team-based round-robin or load-balanced assignment.

## Pattern / Solution
CODEOWNERS-based (built-in, no action needed):
```
# .github/CODEOWNERS
src/payments/   @org/payments-team
*.go            @alice @bob
```
Round-robin with `auto-assign` action:
```yaml
# .github/auto_assign.yml
reviewers:
  - alice
  - bob
  - carol
numberOfReviewers: 2
```
```yaml
on:
  pull_request:
    types: [opened, ready_for_review]
jobs:
  assign:
    runs-on: ubuntu-latest
    steps:
      - uses: kentaro-m/auto-assign-action@v2
        with:
          repo-token: ${{ secrets.GITHUB_TOKEN }}
```

## Gotchas
- CODEOWNERS only requests reviews from code owners; it does not assign them as PR assignees.
- Draft PRs should be excluded — gate the workflow with `if: github.event.pull_request.draft == false`.
- Team slugs in CODEOWNERS require the team to have read access to the repo.
- `auto-assign` picks randomly by default; if reviewers are on vacation the pick is wasted.

## Related
- `branch-protection-and-codeowners.md`
- `github-codeowners-syntax-2026.md`
- `github-actions-label-pr.md`
