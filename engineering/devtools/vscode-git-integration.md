# vscode-git-integration

**Issue:** Developers not using VS Code built-in Git UI effectively
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Staging individual lines, resolving conflicts, and viewing history done only in terminal.

## Pattern / Solution
Use Source Control panel for staging hunks. Use Timeline view for file history. Gutter indicators show added/modified/deleted lines. GitLens adds blame, heatmap, and compare commands.

## Gotchas
- git.autofetch set to true keeps remote state updated in the UI
- Merge conflicts show Accept Current/Incoming/Both inline — use the CodeLens links

## Related
- git-config-global, lazygit-patterns, vscode-extensions-essential
