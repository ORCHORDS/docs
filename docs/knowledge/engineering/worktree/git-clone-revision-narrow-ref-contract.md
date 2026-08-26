# Git clone revision-specific ref contract

**Issue**

A revision-specific clone narrows fetched refs and creates a different local branch and tracking contract from a normal clone.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `--revision` only when the exact ref is reviewed and future fetch behavior is documented.
- Record the resolved object ID and remote URL.
- Do not assume other branches or tags are locally available.

## Verification

1. Clone a branch and tag, inspect refs/config, and fetch later updates.
2. Test missing and moved refs.
3. Verify build provenance uses the resolved commit.

## Gotchas

- A ref name is mutable unless protected.
- Narrow refs can surprise release tooling.
- This is not shallow history by itself.

## Official source

- [Official documentation](https://git-scm.com/docs/git-clone)
