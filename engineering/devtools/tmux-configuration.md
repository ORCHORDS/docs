# tmux-configuration

**Issue:** Long-running processes lost when SSH disconnects; no window management
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SSH session dies, taking running servers with it. No way to have multiple panes in one window.

## Pattern / Solution
Configure ~/.tmux.conf: remap prefix to Ctrl-a, enable mouse mode, set base-index 1. Use tmux new -s dev, tmux attach -t dev. TPM for plugin management. tmux-resurrect persists sessions across reboots.

## Gotchas
- 256-color and true-color require set -g default-terminal tmux-256color
- Nested tmux sessions: use Ctrl-a a for inner prefix

## Related
- terminal-zsh-setup, wezterm-config, iterm2-profiles
