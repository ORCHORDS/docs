# git-config-global

**Issue:** Git global config not set up, causing bad commit authorship and poor defaults
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Commits show wrong email, no default branch set, no difftool configured.

## Pattern / Solution
Set user.name, user.email, init.defaultBranch main, pull.rebase true, push.autoSetupRemote true. Configure core.editor, diff.tool, merge.tool. Use core.autocrlf input on macOS/Linux, true on Windows.

## Gotchas
- Per-repo overrides in .git/config silently win over global — check with git config --list --show-origin
- Signing commits: gpg.signingkey + commit.gpgsign true

## Related
- git-aliases-productivity, conventional-commits
