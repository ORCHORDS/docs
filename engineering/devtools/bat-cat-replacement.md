# bat-cat-replacement

**Issue:** cat shows no syntax highlighting or line numbers; hard to read code in terminal
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Reading source files in terminal with cat is plain text; hard to scan.

## Pattern / Solution
bat file.ts shows syntax-highlighted, line-numbered, git-diffed output with pager. alias cat=bat in shell rc. bat --plain for no decorations. bat --language json for explicit language. Integrates with fzf preview pane.

## Gotchas
- bat uses pager by default — pipe to disable: bat --pager never
- Theme: bat --theme=TwoDark or configure BAT_THEME env var

## Related
- ripgrep-patterns, eza-ls-replacement, fzf-fuzzy-finder
