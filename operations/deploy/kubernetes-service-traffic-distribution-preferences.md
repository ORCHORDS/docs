# Kubernetes Service traffic-distribution preferences

**Issue:** Cluster-wide endpoint selection can add cross-zone cost and latency even when a healthy local endpoint exists.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

On Kubernetes 1.36, use `.spec.trafficDistribution` with `PreferSameZone` or `PreferSameNode` only as a routing preference. Keep readiness correct and enough endpoints in every intended topology; preference is not an availability guarantee or strict locality boundary. Evaluate interactions with internal and external traffic policies, session affinity, topology hints, and the installed proxy implementation.

Choose same-node preference only when node-local placement is deliberate and fallback traffic is acceptable. Measure cost and latency rather than assuming locality always improves them.

## Verification

Generate clients from nodes and zones with local healthy, local unhealthy, and no local endpoints. Inspect EndpointSlices and observed destination topology, then test scale-up, rolling update, node drain, proxy restart, and mixed-version clusters.

## Gotchas

- Preferences can fall back cluster-wide.
- Feature availability depends on the cluster version.
- Local concentration can create endpoint hotspots.

## Official source

- [Kubernetes Service traffic distribution](https://kubernetes.io/docs/concepts/services-networking/service/#traffic-distribution)
