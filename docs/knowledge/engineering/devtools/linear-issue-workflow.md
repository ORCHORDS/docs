# linear-issue-workflow

**Issue:** Issue tracking disconnected from git workflow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Issues in Jira not linked to PRs; status updates require manual context switching.

## Pattern / Solution
Linear auto-links issues from branch names: feat/LIN-123-add-oauth. Branch names with Linear ID auto-close issues on merge. Linear keyboard shortcut C to create issue from anywhere. Cycle workflow: Backlog > Todo > In Progress > Done.

## Gotchas
- Team members must use Linear branch naming convention for auto-close to work
- Priority is P0-P4 — define meaning for your team in Linear settings

## Related
- github-cli-daily-workflow, conventional-commits
