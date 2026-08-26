# git-hooks-husky

**Issue:** Linting and tests not enforced before commits and pushes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Bad code reaches CI because pre-commit checks do not exist or are not committed.

## Pattern / Solution
Install husky + lint-staged. husky init creates .husky/ directory. Add pre-commit hook running npx lint-staged. Configure lint-staged in package.json to run eslint/prettier on staged files only.

## Gotchas
- Husky v9+ uses prepare script — ensure it runs on npm install
- git commit --no-verify bypasses hooks — train team not to use it routinely

## Related
- commitlint-setup, conventional-commits, vscode-eslint-prettier-setup
