# github-milestone-tracking

**Issue:** Using GitHub milestones to track release readiness and sprint progress
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams use milestones for sprint or release tracking but manage them manually. Issues slip past deadlines unnoticed, and milestone burn-down isn't visible without leaving GitHub.

## Pattern / Solution
Milestones group issues and PRs with a due date and completion percentage. Automate their lifecycle with `gh` CLI and Actions.

**Create a milestone via CLI:**
```bash
gh api repos/OWNER/REPO/milestones \
  --method POST \
  --field title="v2.4.0" \
  --field due_on="2026-09-01T00:00:00Z" \
  --field description="Includes auth refactor and payment v2"
```

**Auto-assign milestone to new PRs by branch pattern:**
```yaml
# .github/workflows/milestone.yml
name: Auto-milestone

on:
  pull_request:
    types: [opened]

jobs:
  assign:
    runs-on: ubuntu-latest
    steps:
      - name: Assign milestone from branch
        if: startsWith(github.head_ref, 'release/')
        run: |
          VERSION="${{ github.head_ref }}"
          VERSION="${VERSION#release/}"
          MILESTONE_ID=$(gh api repos/${{ github.repository }}/milestones \
            --jq ".[] | select(.title == \"$VERSION\") | .number")
          if [ -n "$MILESTONE_ID" ]; then
            gh pr edit ${{ github.event.number }} --milestone "$VERSION"
          fi
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Query milestone progress:**
```bash
gh api repos/OWNER/REPO/milestones \
  --jq '.[] | {title, due_on, open_issues, closed_issues, percent: (.closed_issues / (.open_issues + .closed_issues) * 100)}'
```

**Close milestone after release:**
```bash
gh api repos/OWNER/REPO/milestones/MILESTONE_NUMBER \
  --method PATCH \
  --field state=closed
```

## Gotchas
- GitHub only tracks open/closed issue counts per milestone — there's no story points or weight; use Projects v2 for that
- Issues can belong to only one milestone; PRs can also be milestoned separately
- Closed issues in a milestone still count toward the completion percentage — don't close issues as "won't fix" in the milestone if you want the percentage meaningful
- `due_on` must be in ISO 8601 format with time; midnight UTC is conventional
- Milestones are repo-scoped — cross-repo release tracking requires Projects v2 or a dedicated tool

## Related
- `github-projects-v2-2026.md`
- `github-labels-automation.md`
- `github-release-automation-2026.md`
