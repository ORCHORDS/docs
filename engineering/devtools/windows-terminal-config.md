# windows-terminal-config

**Issue:** Windows Terminal not configured for developer workflow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Default Windows Terminal uses cmd.exe with no customization, no font, no keybindings.

## Pattern / Solution
Edit settings.json via Ctrl+comma. Set default profile to WSL2 or PowerShell 7. Configure fontFace: JetBrains Mono, fontSize: 13. Add custom keybindings for splits. Set colorScheme per profile to distinguish environments.

## Gotchas
- startingDirectory uses Windows path format, not Unix
- GPU rendering: set experimental.rendering.forceFullRepaint: false if tearing occurs

## Related
- powershell-profile-setup, wezterm-config, terminal-zsh-setup
