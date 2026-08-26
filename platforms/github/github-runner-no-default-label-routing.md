# GitHub runner no-default-label routing

**Issue:** Registering a self-hosted runner with no default labels removes automatic self-hosted/OS/architecture routing assumptions.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Maintain explicit governed labels, runner groups and route tests; fail closed when exact capacity is absent; document ARC label limitations.

## Tests

Missing/mistyped label, stale runner, cross-OS route, group denial, offline capacity.

## Gotchas

Custom labels describe routing, not trust or capability proof.

## Official sources

- https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow
