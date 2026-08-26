# vim-neovim-basics

**Issue:** Developers switch to Vim/Neovim and get stuck in basic operations
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cannot exit vim, inefficient motion usage, no understanding of modes.

## Pattern / Solution
Core modes: Normal (Esc), Insert (i/a/o), Visual (v/V), Command (:). Key motions: w/b word, f/t find char, ci-quote change inside quotes, % jump brackets. Registers: ay yank to a, ap paste from a.

## Gotchas
- :wq vs :x — :x only writes if changed
- Undo tree: u undo, Ctrl-r redo, g-/g+ traverse undo tree

## Related
- neovim-lsp-setup, neovim-lazy-nvim, helix-editor-basics
