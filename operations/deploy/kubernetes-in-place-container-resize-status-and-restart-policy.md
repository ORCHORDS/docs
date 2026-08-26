# Kubernetes in-place container resize status and restart policy

**Issue:** Updating desired CPU or memory does not prove that a running container received the new allocation, and an unsafe memory decrease can cause disruption or remain pending.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Current Kubernetes supports in-place CPU and memory resize through the Pod `resize` subresource on supported clusters. Desired resources live in the Pod spec; actual applied resources are reported in container status. Observe `PodResizePending` and `PodResizeInProgress`, including Deferred and Infeasible reasons.

Use container `resizePolicy` to state whether CPU or memory changes require restart. `NotRequired` is not a guarantee that every application runtime adapts safely, especially for memory decreases.

## Controls and verification

- Confirm server, kubelet, runtime, and kubectl support before rollout.
- Preserve the Pod's original QoS-class constraints.
- Set restart policy from application runtime behavior.
- Alert on pending, infeasible, and long in-progress resizes.
- Compare desired and actual status resources.
- Canary an increase and decrease under load, verify restart counts and latency, then test deferred capacity and rollback.

## Gotchas

Only supported resource types and container kinds can be resized. A replacement-Pod rollout remains the portable option and may be safer for applications that initialize heap, worker count, or caches from startup resources.

## Sources

- [Kubernetes: Resize CPU and memory assigned to containers](https://kubernetes.io/docs/tasks/configure-pod-container/resize-container-resources/)
- [Kubernetes: Resource management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
