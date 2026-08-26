# Linux recursive mount-attribute policy

**Problem**

Recursive mount attribute changes can unintentionally relax an entire subtree.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only after measuring the relevant operational boundary.

## Controls

- Configure the boundary explicitly and preserve required validation.
- Assign ownership, monitoring, and rollback.
- Apply least privilege.

## Implementation

- Canary before fleet rollout.
- Record effective configuration and version.
- Fail closed on unsupported behavior.

## Tests

- Test boundary, failure, restart, concurrency, and rollback cases.
- Verify no required check is skipped.

## Gotchas

- Version support varies.
- Configuration success does not prove runtime correctness.
- Broad scope can increase impact.

## Official sources

- [Official documentation](https://man7.org/linux/man-pages/man2/mount_setattr.2.html)
