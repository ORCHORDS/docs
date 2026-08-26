# neovim-lazy-nvim

**Issue:** Neovim plugin management is inconsistent across packer/vim-plug/lazy
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Slow startup, manual plugin updates, no lockfile for reproducible installs.

## Pattern / Solution
Bootstrap lazy.nvim in init.lua via git clone to stdpath data. Define plugins as table with opts, config, lazy=true for deferred loading. lazy.lock pins exact commits — commit it. Run :Lazy sync to update.

## Gotchas
- lazy=true with event or ft triggers deferred load — do not lazy-load LSP core plugins
- Profile startup with :Lazy profile to identify slow plugins

## Related
- neovim-lsp-setup, vim-neovim-basics
