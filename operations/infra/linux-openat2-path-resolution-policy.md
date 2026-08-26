# Linux openat2 path-resolution policy

**Issue**

String normalization cannot safely constrain path traversal across symlinks, mount points, and concurrent filesystem changes.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `openat2` relative to a trusted directory descriptor with the required RESOLVE flags.
- Reject unsupported kernels rather than silently weakening containment.
- Operate on returned descriptors instead of re-opening textual paths.

## Verification

1. Test symlinks, magic links, `..`, bind mounts, rename races, and cross-device paths.
2. Run against supported kernels and filesystems.
3. Verify failure codes map to fail-closed behavior.

## Gotchas

- RESOLVE_BENEATH and RESOLVE_IN_ROOT have different semantics.
- Containment is not authorization to file contents.
- Network filesystems can add different behavior.

## Official source

- [Official documentation](https://man7.org/linux/man-pages/man2/openat2.2.html)
