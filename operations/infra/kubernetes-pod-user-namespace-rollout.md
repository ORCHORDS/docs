# Kubernetes Pod user-namespace rollout

**Issue:** Container root can map directly to host root, increasing host impact if another isolation boundary fails.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

On compatible Linux nodes and runtimes, opt Pods into user namespaces with `spec.hostUsers: false`. Verify kernel, idmapped-mount, filesystem, OCI runtime, and CRI support before scheduling. Use labels and admission policy for capable nodes during mixed-fleet rollout. Account for restrictions on host namespaces, raw block devices, and unsupported volumes such as NFS. Continue least-privilege controls; user namespaces reduce impact but do not replace seccomp, capability dropping, or network isolation.

## Verification

Compare `/proc/self/uid_map` inside the Pod and on the host, verify non-overlapping mappings between Pods, test every volume class, and monitor kubelet user-namespace start/error metrics. Attempt an incompatible manifest and ensure admission or scheduling fails predictably.

## Gotchas

- Confirm behavior against the exact deployed version; feature state and defaults can change.
- Preserve logs and artifacts needed to reproduce failures without recording secrets or personal data.
- Roll out behind a reversible change and define the rollback trigger before production use.

## Official source

- [Primary documentation](https://kubernetes.io/docs/concepts/workloads/pods/user-namespaces/)
