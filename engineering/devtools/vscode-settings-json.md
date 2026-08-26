# vscode-settings-json

**Issue:** Configuring VS Code user and workspace settings via settings.json
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
VS Code behavior differs from expected defaults, or settings need to be shared across a team.

## Pattern / Solution
User settings: %APPDATA%\Code\User\settings.json (Windows). Workspace: .vscode/settings.json.

```json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.tabSize": 2,
  "files.autoSave": "onFocusChange",
  "editor.bracketPairColorization.enabled": true
}
```

Open settings JSON: Ctrl+Shift+P > "Open User Settings (JSON)".

## Gotchas
- Workspace settings override user settings for that project only
- Syncing via Settings Sync can overwrite local changes
- Some settings require a window reload to take effect

## Related
- `vscode-workspace-settings.md`
- `vscode-extensions-essential.md`
