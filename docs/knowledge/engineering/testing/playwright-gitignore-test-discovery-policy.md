# Playwright Git-ignore discovery policy

**Issue**

Changing whether test discovery respects .gitignore can unexpectedly omit generated tests or include build/vendor trees.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `respectGitIgnore` explicitly.
- Keep testDir and ignore patterns reviewed.
- Assert expected test counts in required CI.

## Verification

1. Place tests in ignored and nonignored paths.
2. Run list mode and shards.
3. Rename test roots and require failure.

## Gotchas

- Empty discovery can create false confidence.
- Git ignore patterns may be inherited.
- Generated tests need explicit ownership.

## Official source

- [Official documentation](https://playwright.dev/docs/api/class-testconfig#test-config-respect-git-ignore)
