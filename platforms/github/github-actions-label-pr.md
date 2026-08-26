# github-actions-label-pr

**Issue:** Automatically labelling pull requests based on changed files or title
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Large repos need labels applied automatically so reviewers can filter PRs by component without manual triage.

## Pattern / Solution
`.github/labeler.yml`:
```yaml
frontend:
  - changed-files:
    - any-glob-to-any-file: ["src/frontend/**", "*.css"]

backend:
  - changed-files:
    - any-glob-to-any-file: ["src/api/**", "src/db/**"]

docs:
  - changed-files:
    - any-glob-to-any-file: ["docs/**", "*.md"]
```
Workflow:
```yaml
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  label:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/labeler@v5
        with:
          repo-token: ${{ secrets.GITHUB_TOKEN }}
```

## Gotchas
- `actions/labeler@v5` changed the config schema from v4 — `changed-files` is now nested.
- Labels must pre-exist in the repo; the action will error if a label is missing.
- The action runs on `pull_request` events, which means fork PRs get a read-only token — the label write will fail. Use `pull_request_target` for cross-fork support.
- Glob patterns are matched against the full repo-relative path, not the basename.

## Related
- `github-labels-automation.md`
- `github-actions-pr-comment-bot.md`
