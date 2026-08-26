# pre-commit-framework

**Issue:** Git hooks not managed consistently; different languages need different linters
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Python pre-commit hooks break for JS devs; hook scripts are not portable across environments.

## Pattern / Solution
pre-commit framework manages hooks as configuration. .pre-commit-config.yaml lists hooks from public repos. pre-commit install wires to git hooks. pre-commit run --all-files for one-off runs. Hooks run in isolated virtual environments.

## Gotchas
- First run downloads hook environments — can be slow on CI; cache .pre-commit-environments
- pre-commit is Python-based; Node projects may prefer husky + lint-staged instead

## Related
- git-hooks-husky, commitlint-setup, vscode-eslint-prettier-setup
