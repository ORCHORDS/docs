# fzf-fuzzy-finder

**Issue:** History search, file finding, and branch switching done by typing exact names
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Ctrl+R history search is linear; finding files requires remembering exact paths.

## Pattern / Solution
Install fzf, run fzf --bash or add shell key-bindings. Ctrl+R becomes fuzzy history search. Ctrl+T fuzzy file finder. Alt+C fuzzy cd. Compose: git checkout from fzf branch list. Preview: fzf --preview with bat.

## Gotchas
- FZF_DEFAULT_COMMAND can use fd for listing (respects gitignore)
- FZF_DEFAULT_OPTS sets global options like height, layout, keybindings

## Related
- fd-find-patterns, bat-cat-replacement, zoxide-directory-jumper
