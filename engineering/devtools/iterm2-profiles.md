# iterm2-profiles

**Issue:** iTerm2 default config missing key developer features on macOS
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
No hotkey window, no shell integration, repetitive profile setup on new machines.

## Pattern / Solution
Enable Shell Integration via iTerm2 menu. Create profiles with distinct colors per server/environment. Export profiles to JSON and commit. Set up hotkey window for quick terminal access.

## Gotchas
- Shell integration adds iTerm2 marks to prompt — breaks if zsh theme re-renders prompt
- Profiles JSON contains absolute paths — use HOME substitution in scripts

## Related
- terminal-zsh-setup, tmux-configuration, wezterm-config
