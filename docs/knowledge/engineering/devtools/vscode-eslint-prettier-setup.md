# vscode-eslint-prettier-setup

**Issue:** ESLint and Prettier conflict or fail to run on save
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Format on save does not work, or ESLint fixes undo Prettier formatting.

## Pattern / Solution
Install eslint-config-prettier to disable ESLint formatting rules. Set editor.formatOnSave: true and editor.defaultFormatter to prettier-vscode. Configure source.fixAll.eslint in editor.codeActionsOnSave.

## Gotchas
- Never use eslint-plugin-prettier — it is slow and duplicates Prettier's job
- ESLint flat config requires ESLint extension v3+

## Related
- vscode-workspace-settings, vscode-extensions-essential
