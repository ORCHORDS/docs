# Node.js test snapshot update governance

**Issue**

Snapshot update mode can convert an unexpected behavioral change into accepted evidence when review does not distinguish deliberate regeneration from normal verification.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin Node and serializer behavior; keep snapshot files reviewable and deterministic.
- Permit snapshot updates only in an explicit maintainer workflow, never the default CI test command.
- Normalize volatile paths, times, order, and platform-specific values before snapshotting.
- Require semantic assertions beside broad snapshots for security and protocol invariants.

## Verification

1. Run normal verification with updates disabled and prove drift fails.
2. Regenerate twice from a clean checkout and require byte-identical output.
3. Execute supported platform and timezone matrices.

## Gotchas

- Large snapshots hide important changes.
- Custom serializers execute code and belong in the trusted test boundary.
- Updating snapshots is approval, not diagnosis.

## Official source

- [Official documentation](https://nodejs.org/api/test.html#snapshot-testing)
