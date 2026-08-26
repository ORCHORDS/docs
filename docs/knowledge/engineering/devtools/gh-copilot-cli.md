# gh-copilot-cli

**Issue:** Forgetting exact CLI syntax for complex commands
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Constructing complex kubectl, git, awk commands from memory is slow and error-prone.

## Pattern / Solution
Install with gh extension install github/gh-copilot. gh copilot suggest list all pods in crashloopbackoff returns shell command. gh copilot explain explains a command. Alias: alias ?? to gh copilot suggest -t shell.

## Gotchas
- Requires GitHub Copilot subscription
- Suggestions should be reviewed before execution — AI can produce incorrect commands

## Related
- github-cli-daily-workflow, bash-aliases-functions
