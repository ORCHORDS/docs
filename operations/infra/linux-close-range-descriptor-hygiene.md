# Linux close-range descriptor hygiene

**Problem**

Iterating guessed descriptor numbers before exec is racy, inefficient, and can leak privileged descriptors into child processes.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use in launchers, supervisors, and sandbox setup that must close or mark a bounded descriptor range.

## Controls

- Preserve an explicit allowlist for standard and required descriptors.
- Prefer close-on-exec marking when descriptors remain needed before exec.
- Probe kernel/libc support and keep a reviewed fallback.

## Implementation

- Call close_range with exact first/last bounds.
- Use CLOEXEC or UNSHARE flags only for documented lifecycle needs.
- Avoid concurrent descriptor creation during fallback enumeration.

## Tests

- Open sparse high-numbered descriptors and verify inheritance.
- Test threads, fork/exec, unshare mode, unsupported kernels, and resource limits.
- Confirm required descriptors remain usable.

## Gotchas

- Closing a shared descriptor table can affect other threads without unshare semantics.
- Numeric ranges are process-local.
- Descriptor hygiene is not a sandbox by itself.

## Official sources

- [Linux close_range](https://man7.org/linux/man-pages/man2/close_range.2.html)
