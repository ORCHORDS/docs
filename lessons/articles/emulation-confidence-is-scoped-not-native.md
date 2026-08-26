# Emulation confidence is scoped, not native

**Lesson:** Browser viewport emulation, translated binaries, and virtual devices answer useful but narrower questions than native hardware and operating-system execution.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Operationalization

Name the property each lane proves; keep native gates for architecture, signing, device integration, or performance claims that emulation cannot establish.

## Verification

Inject an architecture-only dependency and a device-service dependency; verify emulated lanes do not claim to cover them.

## Gotchas

More emulated matrix rows do not become native evidence through repetition.

## Official sources

- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- https://developer.android.com/studio/run/emulator-acceleration
