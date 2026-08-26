# github-fork-and-pr-workflow

**Issue:** Contributing to a repo via fork and pull request, including keeping forks up to date
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Open-source contributors and external contractors work from forks. Keeping a fork in sync and submitting clean PRs requires specific steps.

## Pattern / Solution
Initial setup:
```bash
gh repo fork owner/repo --clone
cd repo
git remote add upstream https://github.com/owner/repo.git
```
Keeping fork in sync:
```bash
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
```
Creating a PR from a fork:
```bash
git checkout -b feature/my-change
# make changes
git push origin feature/my-change
gh pr create --repo owner/repo --title "My change" --body "..."
```
Allow maintainers to push to your fork's branch:
- When creating the PR, check "Allow edits from maintainers".

## Gotchas
- `gh repo fork` automatically sets up `origin` as your fork and the original as `upstream`.
- Fork PRs run with read-only `GITHUB_TOKEN` — secrets are not available in Actions.
- Use `pull_request_target` carefully for fork PRs that need elevated access — it runs in the base repo context.
- GitHub's "Sync fork" button in the UI does a merge; CLI gives you control over the strategy.

## Related
- `github-squash-vs-merge-vs-rebase.md`
- `github-actions-pr-comment-bot.md`
