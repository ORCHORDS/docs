# neovim-lsp-setup

**Issue:** Neovim has no IDE features without LSP configuration
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
No autocomplete, go-to-definition, or inline diagnostics in Neovim out of the box.

## Pattern / Solution
Use nvim-lspconfig + mason.nvim for server installation. Install language servers via :Mason. Wire up on_attach to set keymaps (gd, K, gr). Add nvim-cmp for completion with cmp-nvim-lsp source.

## Gotchas
- LSP servers must be in PATH or mason-managed; mismatched versions cause silent failures
- vim.diagnostic.config controls inline vs. float display of errors

## Related
- neovim-lazy-nvim, vim-neovim-basics
