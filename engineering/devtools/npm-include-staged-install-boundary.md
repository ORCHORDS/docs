# npm staged dependency inclusion boundary

**Problem**

Including packages marked staged can pull pre-release registry content into installs that normally exclude it.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only in an explicit publisher/test workflow for staged packages.

## Controls

- Keep `include-staged` false in production installs.
- Use isolated registries/accounts and exact versions for staged validation.
- Never combine with release artifact promotion automatically.

## Implementation

- Set the option in a dedicated job.
- Record resolved versions and integrity.
- Discard its lockfile/workspace afterward.

## Tests

- Test normal versus staged metadata, transitive dependencies, cache state, and registry fallback.

## Gotchas

- Staged content is mutable by workflow policy.
- Caches can cross-contaminate normal jobs.
- Support depends on registry behavior.

## Official sources

- [Official documentation](https://docs.npmjs.com/cli/v11/using-npm/config#include-staged)
