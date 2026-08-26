# Kubernetes recursive read-only mount enforcement

**Issue**

A read-only volume mount may still contain writable submounts unless recursive read-only enforcement is requested and supported by the runtime and kernel.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Inventory workloads relying on nested mounts before enabling enforcement.
- Require `readOnly: true` with `recursiveReadOnly: Enabled` for security-sensitive supported volumes.
- Gate admission on node capability and keep unsupported workloads off protected pools.
- Remove write requirements to dedicated explicit volumes.

## Verification

1. Attempt writes at the mount root and every nested mount.
2. Schedule on each runtime/kernel pool and inspect effective pod status.
3. Test projected, CSI, and bind-backed layouts used in production.

## Gotchas

- Enabled enforcement requires readOnly true.
- Runtime support and node capability determine effectiveness.
- Read-only filesystems do not prevent all data exfiltration.

## Official source

- [Official documentation](https://kubernetes.io/docs/concepts/storage/volumes/#recursive-read-only-mounts)
