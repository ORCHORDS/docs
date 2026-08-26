# Kubernetes DaemonSet surge rollout budget

**Issue:** Reusing Deployment rollout assumptions for a node-wide DaemonSet can remove logging, networking, security, or storage coverage from too many nodes, while enabling surge can fail on host-port or node-capacity conflicts.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Choose `RollingUpdate` or `OnDelete` explicitly. For rolling updates, set and review `maxUnavailable`, `maxSurge`, and `minReadySeconds`; do not allow both availability knobs to be zero.
- Size percentages against `desiredNumberScheduled` and account for rounding. Record the maximum simultaneous uncovered and double-podded nodes in the change review.
- Before enabling surge, prove each node can temporarily run old and new Pods together. Check CPU, memory, device claims, host paths, host ports, and singleton processes.
- Gate progress on a readiness signal that proves the node function works, not merely that the container started. Keep an emergency rollback image digest and revision.
- Segment heterogeneous or critical nodes so one bad update cannot remove a control from the entire fleet.

## Verification

Roll a canary node pool, then exercise an unschedulable surge Pod, a never-ready Pod, clock skew with `minReadySeconds`, node loss during rollout, and rollback. Assert the observed unavailable/surge counts never exceed the reviewed budget and run `kubectl rollout status` with a finite deadline.

## Gotchas

- PodDisruptionBudgets do not govern every DaemonSet controller replacement.
- Host-port collisions can make a theoretically affordable surge unschedulable.
- A completed rollout proves controller convergence, not that every node-level function is healthy.

## Official source

- [Kubernetes: perform a rolling update on a DaemonSet](https://kubernetes.io/docs/tasks/manage-daemon/update-daemon-set/)
- [Kubernetes DaemonSet API](https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/daemon-set-v1/)
