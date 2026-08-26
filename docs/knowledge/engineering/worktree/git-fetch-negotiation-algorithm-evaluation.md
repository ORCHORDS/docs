# Git fetch negotiation-algorithm evaluation

**Issue**

Alternative negotiation algorithms trade request rounds and object enumeration differently across repository shapes.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin Git and benchmark default, skipping, and noop only in disposable clones.
- Keep correctness independent of negotiation choice.
- Record protocol version and server behavior.

## Verification

1. Fetch small, stale, partial, and many-ref clones.
2. Compare bytes, rounds, CPU, and resulting refs.
3. Run fsck afterward.

## Gotchas

- Noop can transfer far more data.
- Skipping is a heuristic.
- Server capabilities affect results.

## Official source

- [Official documentation](https://git-scm.com/docs/git-config#Documentation/git-config.txt-fetchnegotiationAlgorithm)
