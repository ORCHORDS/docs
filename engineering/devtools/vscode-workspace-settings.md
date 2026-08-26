# vscode-workspace-settings

**Issue:** Per-project editor settings not committed, causing inconsistency
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Different devs use different tab sizes, rulers, or formatters, causing noisy diffs.

## Pattern / Solution
Commit .vscode/settings.json at repo root. Override user settings per workspace: editor.tabSize, editor.rulers, editor.defaultFormatter. Use [typescript] language overrides for scoped settings.

## Gotchas
- Workspace settings silently win over user settings — document intentional overrides
- Never commit editor.fontSize or personal UI preferences

## Related
- vscode-settings-json, vscode-eslint-prettier-setup
