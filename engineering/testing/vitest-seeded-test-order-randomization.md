# Vitest seeded test-order randomization

**Issue:** Tests that pass only in definition order hide shared-state leakage and become flaky under sharding or parallel execution.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Add a scheduled CI lane using `--sequence.shuffle --sequence.seed=<recorded>`. Randomize both files and tests when isolation is expected, record the seed in artifacts and failure summaries, and make reruns use the identical seed. Keep the normal cache-ordered lane because shuffle gives up Vitest's long-test-first optimization. Reset globals, fake timers, environment variables, servers, and storage in scoped hooks rather than attempting to encode dependencies in ordering.

## Verification

Demonstrate that a deliberately order-dependent fixture fails in the shuffle lane; replay its reported seed locally; then run several fixed seeds as a small regression corpus. A failure must preserve the seed and shard coordinates.

## Gotchas

- Confirm behavior against the exact deployed version; feature state and defaults can change.
- Preserve logs and artifacts needed to reproduce failures without recording secrets or personal data.
- Roll out behind a reversible change and define the rollback trigger before production use.

## Official source

- [Primary documentation](https://vitest.dev/config/sequence)
