# GitHub Actions cross-OS cache archive boundary

**Issue:** Cross-OS cache archives can improve reuse but path, permissions, executable bits and native artifacts differ across operating systems.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Enable only for portable content, key by tool/runtime/architecture where needed, validate restored files, keep build outputs separate.

## Tests

Windows/Linux restore, symlinks, permissions, case collisions, native addon, poisoned cache.

## Gotchas

A cache hit is untrusted optimization evidence, not build correctness.

## Official sources

- https://github.com/actions/cache
