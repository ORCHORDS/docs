# github-branch-naming-conventions

**Issue:** Establishing and enforcing branch naming conventions across a team
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Inconsistent branch names make it hard to identify purpose, link to tickets, or apply branch-based automation (labelling, CI filters).

## Pattern / Solution
Common patterns:
```
feature/TICKET-123-short-description
fix/TICKET-456-bug-description
chore/update-dependencies
release/v1.4.0
hotfix/critical-auth-bypass
```
Enforce with a workflow:
```yaml
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  check-branch:
    runs-on: ubuntu-latest
    steps:
      - name: Validate branch name
        run: |
          if ! echo "${{ github.head_ref }}" | grep -qE '^(feature|fix|chore|release|hotfix)/.+'; then
            echo "Branch name must start with feature/, fix/, chore/, release/, or hotfix/"
            exit 1
          fi
```
Enforce with GitHub Rulesets (no workflow needed):
- Settings → Rules → Rulesets → Branch name pattern: `(feature|fix|chore|release|hotfix)/**`

## Gotchas
- Spaces and special characters in branch names cause issues with many shell tools; use hyphens.
- Forward slashes create visual hierarchy in GitHub's branch list — use them.
- Do not include full JIRA URLs — just the ticket ID.
- Rulesets apply even to admins unless you specifically bypass them.

## Related
- `github-rulesets-2026.md`
- `github-commit-message-conventions.md`
