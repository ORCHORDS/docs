# zoxide-directory-jumper

**Issue:** Navigating to frequently used directories requires typing long paths
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
cd ~/projects/company/frontend/src typed dozens of times per day.

## Pattern / Solution
Install zoxide, add eval to shell rc. z front jumps to most frecent directory matching front. zi for interactive selection with fzf. z - for previous directory. Builds frecency index from cd history automatically.

## Gotchas
- Must visit directories at least once before z recognizes them
- Replaces cd with z — some scripts using cd will not build frecency

## Related
- fzf-fuzzy-finder, bash-aliases-functions
