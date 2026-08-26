# fd-find-patterns

**Issue:** find command syntax is non-intuitive and slow; ignores gitignore
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
find . -name *.ts -not -path */node_modules/* is verbose and fragile.

## Pattern / Solution
fd .ts finds TypeScript files, automatically excluding gitignored paths. fd -t d for directories. fd -e ts by extension. fd --exec to run command on results. fd -H includes hidden files.

## Gotchas
- fd uses regex, not glob — escape literal dots with backslash
- Install as fd-find on Debian/Ubuntu (binary named fdfind); alias fd=fdfind

## Related
- ripgrep-patterns, fzf-fuzzy-finder
