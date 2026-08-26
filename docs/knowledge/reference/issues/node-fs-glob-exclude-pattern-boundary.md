# Node fs.glob exclude-pattern boundary

**Issue:** Node fs.glob include/exclude semantics and cwd/path options can select unintended files in packaging or cleanup.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Pin Node, anchor cwd, separate include/exclude policy, resolve and validate every result before mutation.

## Tests

Dotfiles, symlinks, parent traversal, platform separators, empty and overlapping patterns.

## Gotchas

A glob match is not authorization; never delete from unresolved user patterns.

## Official sources

- https://nodejs.org/api/fs.html#fspromisesglobpattern-options
