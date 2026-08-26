# oh-my-zsh-plugins

**Issue:** Oh My Zsh installed but plugins not configured, causing slow startup
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Default OMZ install is slow (400ms+) and underutilizes the plugin ecosystem.

## Pattern / Solution
Enable only needed plugins in .zshrc plugins=(). Essential: git, docker, kubectl, fzf. Use zinit or antidote instead of OMZ for faster plugin loading with lazy init. Profile with zsh -i -c exit timing.

## Gotchas
- Each plugin adds startup time; measure before adding
- oh-my-zsh updates can overwrite theme customizations — use themes via ZSH_CUSTOM

## Related
- terminal-zsh-setup, starship-prompt
