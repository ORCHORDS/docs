# Kubernetes OCI Image Volumes and Rollout Controls

**Issue:** OCI artifacts mounted as Kubernetes image volumes can simplify distribution of read-only models, rules, or static data, but mutable references and pull failures can make rollouts nondeterministic or block Pod startup.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use `spec.volumes[].image` only on a cluster version where the feature state is supported. The Kubernetes documentation marks image volumes stable and enabled by default in v1.36; older versions have different feature-gate requirements.

Reference production artifacts by digest, keep the mount read-only, and use registry retention that preserves deployed digests. Select pull policy deliberately:

- `Always` resolves/pulls at each Pod startup and fails startup if resolution fails.
- `IfNotPresent` reuses local content when available.
- `Never` requires the artifact already exist on the node.

Apply registry authentication through node, service-account, or Pod image-pull credentials. Enforce allowed registries and digest use with admission policy. Treat the artifact and application as one release manifest so rollback restores both.

## Verification

- Schedule onto an empty node to test a real pull, authentication, unpacking, and startup latency.
- Deny registry access and confirm the Pod fails visibly rather than starting with unexpected content.
- Recreate the Pod after publishing a new tag and prove why digest pinning is required.
- Verify artifact format support with every production container runtime.
- Scan/sign the artifact and enforce the same provenance policy used for container images.
- Run application correctness checks against the mounted content and retain them in every rollout.

## Gotchas

The volume is resolved at Pod startup and pull failure blocks containers. Runtime implementations determine supported OCI object types. `fsGroupChangePolicy` has no effect for this volume type, and `subPath` support depends on Kubernetes version. Image volumes are distribution, not writable persistence.

## Sources

- [Kubernetes volumes: image](https://kubernetes.io/docs/concepts/storage/volumes/#image)
- [Use an image volume with a Pod](https://kubernetes.io/docs/tasks/configure-pod-container/image-volumes/)
- [Kubernetes images and pull policy](https://kubernetes.io/docs/concepts/containers/images/)
