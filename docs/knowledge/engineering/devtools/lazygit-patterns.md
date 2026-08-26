# lazygit-patterns

**Issue:** Complex git operations require many terminal commands; no visual overview
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Staging individual hunks, interactive rebasing, and resolving conflicts is slow in CLI.

## Pattern / Solution
lazygit TUI shows files, commits, branches, stash in panels. Stage hunks with Space. Interactive rebase in commits panel with e. Cherry-pick across branches. Resolve conflicts with built-in diff view. Alias: alias lg=lazygit.

## Gotchas
- Learning curve for keybindings — ? shows help in each panel
- Custom commands configurable in ~/.config/lazygit/config.yml

## Related
- vscode-git-integration, git-interactive-rebase, git-stash-patterns
