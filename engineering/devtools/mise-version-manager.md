# mise-version-manager

**Issue:** Multiple runtime version managers add complexity
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Team uses nvm for Node, pyenv for Python, rbenv for Ruby — three separate tools to maintain.

## Pattern / Solution
mise (formerly rtx) manages all runtimes. mise use node@20 python@3.12 in project. Creates .mise.toml. Reads .node-version, .nvmrc, .python-version. eval mise activate zsh in shell rc.

## Gotchas
- mise shims vs direct activation — direct activation is faster but shims work in non-interactive shells
- Plugin system extends to any tool: postgres, terraform, kubectl

## Related
- nvm-node-version-manager, fnm-node-manager, direnv-env-setup
