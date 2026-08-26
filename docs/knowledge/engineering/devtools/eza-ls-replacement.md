# eza-ls-replacement

**Issue:** ls shows no git status, icons, or tree view
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Standard ls -la lacks file git status, file type icons, and tree visualization.

## Pattern / Solution
eza -la --git --icons shows long format with git status and Nerd Font icons. eza --tree --level=2 for tree view. Add aliases: alias ls=eza, alias ll=eza-la-git-icons, alias lt=eza-tree-level2.

## Gotchas
- Icons require Nerd Font in terminal; without it, shows garbled characters
- eza is the maintained fork of exa (abandoned) — install eza not exa

## Related
- bat-cat-replacement, starship-prompt
