# Kubernetes parallel image-pull budget

**Problem**

Unbounded parallel image pulls can saturate node disk and network; serialized pulls can make scale-up unnecessarily slow.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when nodes pull multiple large images during bursts or rollouts.

## Controls

- Set `serializeImagePulls` and `maxParallelImagePulls` from node measurements.
- Protect registry rate limits and node disk headroom.
- Keep image verification and digest pinning unchanged.

## Implementation

- Canary kubelet configuration on one node pool.
- Pre-pull only reviewed immutable images.
- Monitor pull duration, failures, disk IO, and registry throttling.

## Tests

- Test cold/warm nodes, multiple Pods, registry 429s, disk pressure, and restart.
- Prove required admission checks still run.

## Gotchas

- The maximum setting depends on serialized pulls being disabled.
- More concurrency can be slower.
- Cached images change benchmarks.

## Official sources

- [Official documentation](https://kubernetes.io/docs/concepts/containers/images/#maximum-parallel-image-pulls)
