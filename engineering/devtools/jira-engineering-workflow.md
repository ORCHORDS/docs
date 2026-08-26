# jira-engineering-workflow

**Issue:** Jira configured for project management, not optimized for developer workflow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers avoid updating Jira because it is slow and context-switching is painful.

## Pattern / Solution
Use Smart Commits from git: commit message with PROJ-123 #done. Jira automation to transition issues on PR events. Jira CLI for terminal-based updates. Custom workflows matching your team's actual process.

## Gotchas
- Smart Commits require Jira app linked to GitHub/Bitbucket
- Issue key in commit must be in subject line, not body, for Smart Commit parsing

## Related
- linear-issue-workflow, conventional-commits, github-cli-daily-workflow
