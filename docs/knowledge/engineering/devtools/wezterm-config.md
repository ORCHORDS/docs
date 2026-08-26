# wezterm-config

**Issue:** Terminal emulator not configured for GPU acceleration, fonts, or multiplexing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Default terminal is slow, lacks ligatures, and requires tmux for pane splitting.

## Pattern / Solution
Configure ~/.wezterm.lua in Lua. Set font, enable_tab_bar, keybindings for splits. WezTerm has built-in multiplexing — use instead of tmux for local sessions. GPU rendering via front_end = WebGpu.

## Gotchas
- Lua config errors crash WezTerm silently — use wezterm show-keys to debug
- Multiplexing works locally but tmux still needed for remote sessions

## Related
- tmux-configuration, starship-prompt, iterm2-profiles
