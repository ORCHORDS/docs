# Govern Cross-Platform Parity with a Capability Register

**Issue:** A single “supported on mobile and desktop” label hides whether each shell supports the same user outcome, a reduced outcome, or no outcome across windows, input methods, permissions, and lifecycle states.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Lesson

Track parity at the capability and user-outcome level, not at the screen-name level. A platform can use a different layout or native mechanism and still achieve parity; visual sameness can conceal a missing or unsafe capability.

## Controls

- Maintain a register keyed by stable capability ID, with owner, supported shells, lifecycle state, prerequisite, data contract, accessibility expectation, offline behavior, and maturity.
- Classify each platform as equivalent, adapted, intentionally unavailable, experimental, or unknown; require evidence and a review date.
- Define critical end-to-end journeys separately from optional enhancements.
- Link each capability to contract, integration, accessibility, and platform-configuration tests.
- Update the register in the same change that introduces, removes, gates, or materially adapts a capability.
- Treat resizable windows, multiple instances, foldable posture, and external input as dimensions, not new platform names.
- Publish user-facing availability from the same governed source where practical.

## Verification

- Generate a parity-diff in release review and fail when a critical cell is unknown or regresses without approval.
- Execute representative journeys across supported window sizes, display modes, and input combinations.
- Trace a sampled register row to shipped code, tests, telemetry, help, and release notes.
- Confirm unavailable features fail clearly rather than leaving dead controls or unreachable state.

## Gotchas

Feature flags describe exposure, not parity. Matching navigation labels do not prove matching outcomes. The register should not force inappropriate uniformity; it makes adaptation and gaps explicit.

## Official sources

- [Android adaptive app quality guidelines](https://developer.android.com/develop/adaptive-apps/quality-guidelines/adaptive-app-quality)
- [Apple interface fundamentals](https://developer.apple.com/documentation/technologyoverviews/interface-fundamentals)
