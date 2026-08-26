# zed-editor-patterns

**Issue:** Zed editor setup and collaboration features not understood
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams trial Zed but do not know how to configure it or use multiplayer features.

## Pattern / Solution
Config lives at ~/.config/zed/settings.json. Install language extensions from Extensions panel. Use zed collab for real-time collaboration. Built-in terminal via Ctrl+backtick. LSP support is native for most languages.

## Gotchas
- Plugin ecosystem much smaller than VS Code — check extension availability before committing team-wide
- GPU-accelerated rendering means higher baseline GPU usage; issue on older hardware

## Related
- vscode-settings-json, neovim-lsp-setup
