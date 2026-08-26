# Git selective pack-refs optimization

**Issue**

Packing every ref can harm frequently updated namespaces or third-party tooling; selective include/exclude and auto modes need measured policy.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `git pack-refs --auto` as the default maintenance path.
- Apply include/exclude patterns only to documented namespaces.
- Quiesce incompatible ref writers and preserve recovery procedures.

## Verification

1. Benchmark lookup/update with production ref shapes.
2. Verify refs, reflogs, fetch, push, and worktree operations afterward.
3. Test pattern precedence and empty matches.

## Gotchas

- Packed refs remain mutable through Git commands.
- Direct file editing is unsafe.
- Reftable repositories have different optimization mechanics.

## Official source

- [Official documentation](https://git-scm.com/docs/git-pack-refs)
