# Linux pidfd race-free process control

**Issue:** PID reuse creates time-of-check/time-of-use races when supervisors signal or wait for a process identified only by an integer.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Open a pidfd while the intended process identity is known and use pidfd-aware polling, waiting, signaling, and descriptor duplication where supported. Treat pidfds as capabilities: apply ordinary descriptor ownership, inheritance, and lifetime controls. Detect kernel and libc support, and keep a fallback that revalidates process identity rather than silently reverting to unsafe PID-only signaling.

## Verification

Force rapid PID churn and prove a stale handle cannot signal a replacement process. Test exit before registration, exec, namespace boundaries, permissions, descriptor passing, supervisor restart, and resource limits.

## Gotchas

- Pin and verify exact platform versions before rollout.
- Preserve reproducible diagnostics without secrets or personal data.
- Define rollback and stop conditions before production use.

## Official source

- [Primary documentation](https://man7.org/linux/man-pages/man2/pidfd_open.2.html)
