# Linux process_mrelease reclaim boundary

**Problem**

Reclaiming memory from a dying process can speed recovery but is a privileged destructive action tied to precise process lifetime.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only in supervised OOM/recovery tooling after the target is already exiting.

## Controls

- Acquire a pidfd and verify target identity/state.
- Restrict capability and audit every invocation.
- Never use it as ordinary application memory management.

## Implementation

- Call through a bounded recovery agent.
- Handle races and unsupported kernels as non-success.
- Preserve diagnostics first.

## Tests

- Test live, exiting, exited, reused PID, permission denial, and repeated calls.

## Gotchas

- The target must be in the right exit state.
- Reclaimed diagnostics may be lost.
- Pidfds solve identity, not authorization.

## Official sources

- [Official documentation](https://man7.org/linux/man-pages/man2/process_mrelease.2.html)
