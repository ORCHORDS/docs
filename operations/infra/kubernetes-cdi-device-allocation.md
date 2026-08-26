# Kubernetes CDI device allocation boundary

**Problem**

CDI-qualified device references let plugins inject device configuration into containers, extending the trusted node/runtime configuration surface.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for device plugins and DRA integrations with governed CDI specs.

## Controls

- Trust only node-managed CDI spec directories.
- Pin device-plugin/runtime versions.
- Restrict workloads allowed to request devices.

## Implementation

- Publish stable qualified names.
- Validate allocated devices and injected edits.
- Audit spec changes.

## Tests

- Test missing/duplicate specs, runtime restart, plugin failure, multi-device Pods, cleanup, and node drain.

## Gotchas

- CDI specs can inject mounts/env/hooks.
- Node compromise defeats isolation.
- Availability differs by runtime/version.

## Official sources

- [Official documentation](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/device-plugins/)
