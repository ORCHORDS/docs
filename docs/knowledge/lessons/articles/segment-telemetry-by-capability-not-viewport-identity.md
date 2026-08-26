# Segment Experience Telemetry Without Treating Viewport as Identity

**Issue:** Labeling events “mobile” or “desktop” from viewport width confounds form factor, resizable windows, input capability, browser, and operating system. It can hide parity failures and creates unstable cohorts.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Lesson

Instrument the dimensions needed to explain an experience—shell, release, window class, input capability, lifecycle, and feature state—while keeping them low-cardinality and privacy reviewed. Viewport is an observation at an event time, not a durable device or user identity.

## Controls

- Define a controlled taxonomy for application shell and supported window-size buckets.
- Record capability signals only when relevant, such as coarse primary pointer or hover availability; allow unknown.
- Use standard browser/platform semantic attributes when available and preserve their documented stability level.
- Attach app version, capability ID, experiment or flag state, lifecycle state, and journey step to parity telemetry.
- Bound cardinality: bucket dimensions, prohibit raw viewport values in metric labels, and keep detailed diagnostics in sampled events.
- Avoid persistent hardware identifiers and unnecessary device models; perform privacy, retention, and access review.
- Never use a telemetry-derived form-factor class for authorization or product eligibility.

## Verification

- Resize and move the same session across window classes and confirm event classification changes without creating a new identity.
- Compare hybrid touch-and-pointer devices, narrow desktop windows, tablets, and mobile browsers requesting desktop presentation.
- Assert unknown browser or platform hints stay unknown rather than being guessed.
- Run metric-cardinality and privacy-schema checks in CI.
- Reconcile capability-level success and failure rates across shells without aggregating incompatible journey definitions.

## Gotchas

A mobile hint is not a physical-device proof, and browser semantic attributes may be developmental. User-agent strings and device IDs increase privacy and cardinality risk. Segmentation can reveal disparity; it does not itself establish why the disparity exists.

## Official sources

- [OpenTelemetry browser semantic conventions](https://opentelemetry.io/docs/specs/semconv/resource/browser/)
- [OpenTelemetry device attributes and privacy warning](https://opentelemetry.io/docs/specs/semconv/registry/attributes/device/)
- [W3C Media Queries Level 5](https://www.w3.org/TR/mediaqueries-5/)
