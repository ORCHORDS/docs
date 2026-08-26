# github-stale-bot-config

**Issue:** Automatically closing stale issues and PRs using the actions/stale action
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Issue trackers accumulate hundreds of stale issues that nobody will ever fix. Manually triaging them wastes maintainer time. `actions/stale` automates labeling and closing with configurable windows.

## Pattern / Solution
Add a scheduled workflow that runs `actions/stale@v9`.

**`.github/workflows/stale.yml`:**
```yaml
name: Close stale issues and PRs

on:
  schedule:
    - cron: '30 1 * * *'    # 01:30 UTC daily
  workflow_dispatch:          # allow manual runs for testing

permissions:
  issues: write
  pull-requests: write

jobs:
  stale:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/stale@v9
        with:
          # Issues
          days-before-issue-stale: 60
          days-before-issue-close: 14
          stale-issue-label: stale
          stale-issue-message: >
            This issue has been automatically marked as stale because it has
            not had recent activity. It will be closed in 14 days if no
            further activity occurs.
          close-issue-message: Closing due to inactivity.
          close-issue-reason: not_planned

          # PRs
          days-before-pr-stale: 30
          days-before-pr-close: 14
          stale-pr-label: stale
          stale-pr-message: >
            This PR has been automatically marked as stale. Please rebase and
            update or it will be closed in 14 days.
          close-pr-message: Closing stale PR.

          # Exemptions
          exempt-issue-labels: 'pinned,security,roadmap'
          exempt-pr-labels: 'pinned,do-not-close'
          exempt-all-milestones: true   # don't close milestoned issues

          operations-per-run: 100       # API rate limit guard
```

**Exempt specific assignees:**
```yaml
          exempt-assignees: 'bot-user,dependabot[bot]'
```

## Gotchas
- `operations-per-run` defaults to 30 — repos with many issues need this bumped or the job won't process all stale candidates in one run
- The action counts calendar days from the last event (comment, label, commit for PRs) — not from creation date
- Adding any label or comment to an issue resets the stale clock, so a single "thanks for reporting" reply keeps an issue alive indefinitely
- `close-issue-reason: not_planned` marks the issue as "not planned" in the GitHub UI; omit it to use the default "completed" reason
- Running daily at midnight UTC causes thundering-herd API usage; offset the cron to off-peak hours

## Related
- `github-labels-automation.md`
- `github-milestone-tracking.md`
- `github-issue-forms-2026.md`
