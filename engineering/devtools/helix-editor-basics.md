# helix-editor-basics

**Issue:** Modal editor with LSP and tree-sitter baked in, but unfamiliar UX
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Vim users try Helix but are confused by selection-first model vs Vim's action-first.

## Pattern / Solution
Helix is selection-first: select then act (opposite of Vim). w selects word, d deletes selection. gd go to definition, gr find references — LSP built in. space+f file picker. Multiple cursors: C duplicate cursor. Tutor: hx --tutor.

## Gotchas
- No plugin system (by design) — all features must be built-in
- Config at ~/.config/helix/config.toml; themes at ~/.config/helix/themes/

## Related
- vim-neovim-basics, neovim-lsp-setup
