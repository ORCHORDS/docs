# git-aliases-productivity

**Issue:** Long git commands typed in full, reducing velocity
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
git checkout -b, git log --oneline --graph, git push --force-with-lease typed repeatedly.

## Pattern / Solution
Add to ~/.gitconfig [alias] section: co = checkout, br = branch, lg = log --oneline --graph --decorate, fpush = push --force-with-lease, recent = branch --sort=-committerdate.

## Gotchas
- Git aliases run in shell with ! prefix
- Aliases are global; document team aliases in onboarding docs

## Related
- git-config-global, bash-aliases-functions
