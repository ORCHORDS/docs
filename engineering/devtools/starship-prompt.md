# starship-prompt

**Issue:** Shell prompt gives no context about git state, language versions, or errors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Plain PS1 shows no branch, no node version, no last exit code — context switching is blind.

## Pattern / Solution
Install starship, add eval to .zshrc. Configure ~/.config/starship.toml. Use presets: starship preset nerd-font-symbols. Modules: git_branch, git_status, nodejs, duration.

## Gotchas
- Requires Nerd Font in terminal emulator for icons to render
- command_timeout setting prevents slow git status from blocking prompt

## Related
- terminal-zsh-setup, oh-my-zsh-plugins, wezterm-config
