# ripgrep-patterns

**Issue:** grep is slow on large codebases and ignores .gitignore
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
grep -r on large repo takes seconds and returns results from node_modules.

## Pattern / Solution
rg pattern respects .gitignore and is 5-10x faster than grep. rg -t js TODO filters by file type. rg -l lists files only. rg --fixed-strings disables regex. -A/-B/-C for context lines. rg --glob !dist/ excludes patterns.

## Gotchas
- rg uses Rust regex syntax — some PCRE features unavailable without --pcre2
- Config file: ~/.ripgreprc with --smart-case, --hidden etc.

## Related
- fd-find-patterns, fzf-fuzzy-finder, bat-cat-replacement
