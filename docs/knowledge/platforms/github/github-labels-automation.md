# github-labels-automation

**Issue:** Automatically applying labels to PRs and issues based on paths, content, or type
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
PRs arrive unlabeled, making filtering and triage impossible. Maintainers manually add labels which is inconsistent and time-consuming.

## Pattern / Solution
Two tools cover most cases: `actions/labeler` for path-based PR labeling, and `github-actions-ecosystem/action-add-labels` for rule-based issue labeling.

**Path-based PR labeler (`.github/labeler.yml`):**
```yaml
# .github/labeler.yml
frontend:
  - changed-files:
      - any-glob-to-any-file:
          - 'apps/web/**'
          - 'packages/ui/**'

backend:
  - changed-files:
      - any-glob-to-any-file:
          - 'services/**'
          - 'packages/api-client/**'

documentation:
  - changed-files:
      - any-glob-to-any-file:
          - '**/*.md'
          - 'docs/**'

ci:
  - changed-files:
      - any-glob-to-any-file:
          - '.github/**'
```

**Labeler workflow (`.github/workflows/labeler.yml`):**
```yaml
name: Label PRs

on:
  pull_request_target:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  label:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/labeler@v5
        with:
          repo-token: ${{ secrets.GITHUB_TOKEN }}
          sync-labels: true    # remove labels for paths no longer changed
```

**Label issues by type from issue form:**
```yaml
# In issue form template (.github/ISSUE_TEMPLATE/bug.yml)
labels: ['bug', 'needs-triage']
```

**Sync labels across repos (define labels as code):**
```bash
# Using github-label-sync npm tool
npx github-label-sync \
  --access-token "$GH_TOKEN" \
  --labels .github/labels.json \
  owner/repo
```

```json
[
  {"name": "bug", "color": "d73a4a", "description": "Something isn't working"},
  {"name": "enhancement", "color": "a2eeef", "description": "New feature or request"}
]
```

## Gotchas
- Use `pull_request_target` (not `pull_request`) for the labeler so it has write permissions even on fork PRs — but never run untrusted code in `pull_request_target` jobs
- `sync-labels: true` removes labels the labeler didn't add — be careful if humans also apply labels manually
- `actions/labeler@v5` changed the config format from v4 — the `changed-files` key and glob syntax changed; v4 configs need migration
- Labels must already exist in the repo before they can be applied — the action won't create them
- Issue form `labels:` in YAML frontmatter applies labels at creation; they can be removed by humans afterward

## Related
- `github-issue-forms-2026.md`
- `github-stale-bot-config.md`
- `github-milestone-tracking.md`
