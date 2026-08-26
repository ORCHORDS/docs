# github-cli-daily-workflow

**Issue:** Switching to browser for PR creation, review, and issue management breaks flow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
PR creation, review status checking, and issue creation require browser context switches.

## Pattern / Solution
gh pr create --fill creates PR from branch name and commits. gh pr list shows open PRs. gh pr checkout 123 switches to PR branch. gh pr review --approve. gh run list checks CI. gh issue create, gh repo clone.

## Gotchas
- gh auth login required once; stores token in system keychain
- --fill uses first commit message as title — ensure conventional commits

## Related
- git-config-global, conventional-commits, gh-copilot-cli
