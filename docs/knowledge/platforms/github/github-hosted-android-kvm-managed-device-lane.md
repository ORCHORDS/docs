# GitHub-hosted Android KVM managed-device lane

**Issue:** GitHub-hosted Linux supports hardware acceleration for Android SDK tools. Android's emulator uses KVM on Linux, while Gradle Managed Devices can provision repeatable virtual-device specifications for CI.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Run an acceleration preflight and fail if KVM is unavailable; define API level, device, image source, locale, and orientation in versioned Gradle configuration.
- Use a small PR smoke device and a bounded nightly matrix; cache dependencies, not mutable emulator state.
- Pin Android SDK/AGP/Gradle inputs and keep signing keys out of PR workflows.

## Verification

1. Run lint/unit/assemble before the device lane.
2. Boot the managed device from clean state, execute instrumentation, and collect JUnit/logcat/screenshots on failure.
3. Exercise cancellation and prove emulator processes and temporary data are removed.

## Gotchas

Software emulation can turn a capacity fault into extreme slowness. Browser emulation is not an Android-device test, and an emulator matrix is not equivalent to physical-device coverage.

## Official sources

- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- https://developer.android.com/studio/run/emulator-acceleration
- https://developer.android.com/training/testing/different-screens/tools
