# Helm post-renderer trust boundary

**Problem**

A post-renderer can rewrite every rendered Kubernetes object after chart review and before apply.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only for governed transformations that cannot be expressed safely in values or chart templates.

## Controls

- Pin and authenticate the executable.
- Review input/output diffs and prohibit secret logging.
- Run under least filesystem/network privilege.

## Implementation

- Apply deterministic transformations.
- Validate rendered output after post-rendering.
- Record renderer digest with release evidence.

## Tests

- Test malicious/invalid output, nondeterminism, hooks, CRDs, secrets, rollback, and renderer failure.

## Gotchas

- Post-renderers execute local code.
- All collaborators must use the same renderer.
- Chart signatures do not attest transformed manifests.

## Official sources

- [Official documentation](https://helm.sh/docs/topics/advanced/#post-rendering)
