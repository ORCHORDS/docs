# Upstream Deprecation Signal to Migration Deadline

**Issue:** Teams often record upstream deprecations but do not convert them into owned migration deadlines, causing emergency upgrades when support ends.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Ingest release notes, runtime warnings, and lifecycle notices into one dependency record.
- Record first affected version, removal or end-of-support date, replacement path, owner, and latest safe completion date.
- Budget migration work before the final supported release and test it against representative workloads.
- Escalate when the completion date crosses the dependency’s support window.

## Verification

- Seed a synthetic end-of-support notice and verify ownership and escalation.
- Run the replacement in CI and compare behavior, performance, and rollback compatibility.
- Audit closed migrations for removal of compatibility shims and warning suppressions.

## Gotchas

- A deprecation warning may appear only on rarely exercised code paths.
- Vendor extended support is a risk decision, not an automatic substitute for migration.

## Official sources

- https://sre.google/sre-book/managing-critical-state/
