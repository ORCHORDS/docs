# Android emulator CI hangs without KVM preflight

**Issue:** Instrumentation jobs that silently fall back from KVM acceleration can appear flaky or hang until the workflow timeout. Diagnose capability before downloading images or starting an emulator.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Run the emulator acceleration check and verify device access before boot.
- Use Gradle Managed Devices with an AOSP ATD image where appropriate, fixed device/API inputs, bounded boot/test timeouts, and one retry only for classified infrastructure failures.
- Upload logs even when boot fails and terminate all emulator/adb processes in final cleanup.

## Verification

1. Remove KVM access and confirm a fast, explanatory failure.
2. Simulate boot timeout, test timeout, and cancellation.
3. Confirm retry policy never retries deterministic assertion failures.

## Gotchas

Adding more workflow timeout hides the cause and consumes capacity. Do not weaken test selection merely to compensate for an unaccelerated host.

## Official sources

- https://developer.android.com/studio/run/emulator-acceleration
- https://developer.android.com/studio/projects/continuous-integration
