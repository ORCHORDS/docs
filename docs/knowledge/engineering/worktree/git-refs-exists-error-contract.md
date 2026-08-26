# Git refs exists exit-code contract

**Issue**

Scripts that conflate a missing ref with a reference-database error can create or overwrite refs during corruption or I/O failure.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `git refs exists` and distinguish exit 0, 2, and 1.
- Fail closed on errors other than absence.
- Validate the ref name separately before creation.

## Verification

1. Test present, missing, malformed, corrupt, and unreadable refs.
2. Run across supported ref backends.
3. Race deletion and creation through supported transactions.

## Gotchas

- Existence does not prove object reachability.
- Ref validation and lookup are separate.
- Older Git versions may lack the command.

## Official source

- [Official documentation](https://git-scm.com/docs/git-refs)
