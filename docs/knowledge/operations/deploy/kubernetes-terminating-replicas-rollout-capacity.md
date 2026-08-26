# Kubernetes terminating replicas and rollout capacity accounting

**Issue:** During a rolling Deployment, terminating Pods can continue consuming CPU, memory, volumes, and shutdown time after replacements start, so live usage can exceed desired and surge replica counts.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Capacity-plan for terminating as well as available and updated replicas. Set `terminationGracePeriodSeconds` from measured shutdown behavior, keep preStop hooks bounded, and expose terminating-replica status where supported. Align `maxSurge` and `maxUnavailable` with real node headroom and disruption objectives.

## Verification

Run a staging rollout with slow graceful termination. Observe deletion timestamps, scheduler placement, node utilization, volume detach behavior, peak resource use, and availability. Confirm forced termination remains exceptional.

## Gotchas

Terminating Pods are not available but may consume full resources. Status fields and feature gates vary by release. Shortening graceful shutdown merely for rollout speed can drop work.

## Official sources

- https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#terminating-pods
- https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination
