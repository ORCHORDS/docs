# Compute Pressure adaptive-work boundary

**Issue:** Compute Pressure exposes coarse system pressure states for adaptive workloads. Using it as a benchmark, device fingerprint, or immediate UI switch creates unstable behavior and privacy risk.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental

## Controls and implementation
Feature-detect support, request only documented sources, and treat states as coarse hints. Apply hysteresis, minimum dwell time, and bounded quality tiers; preserve user choice and a deterministic unsupported fallback. Reduce optional work such as animation detail or background computation, never correctness, security checks, or data durability.

## Verification
Test unsupported/denied contexts, rapid state changes, background tabs, thermal/load changes, observer lifecycle, multiple consumers, reduced motion, and recovery. Confirm adaptations do not oscillate or expose raw device classification.

## Gotchas
Pressure includes system factors outside the page and does not identify the cause. Values are intentionally coarse and implementation-dependent.

## Sources
- W3C Devices and Sensors WG, [Compute Pressure](https://www.w3.org/TR/compute-pressure/)
- W3C, [Permissions](https://www.w3.org/TR/permissions/)
