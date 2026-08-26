# Apple SensitiveContentAnalysis consent boundary

**Issue:** An app scans user-selected media without a clear safety purpose or treats a framework result as proof of illegal content or user intent.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer Apple platform API; gate by OS availability

SensitiveContentAnalysis can support on-device detection and intervention for sensitive imagery. Use it only in a documented safety flow, minimize media handling, and keep enforcement/human-support policy separate from a probabilistic result.

**Source:** [Apple SensitiveContentAnalysis documentation](https://developer.apple.com/documentation/sensitivecontentanalysis)

## Controls

- invoke only for the explicit product surface and supported media;
- keep analysis on-device where the API provides it;
- disclose intervention behavior and offer appropriate user choices;
- avoid logging media or raw results broadly;
- gate by availability and define a privacy-preserving fallback;
- require separate evidence for punitive account action.

## Verification

Test unavailable/disabled state, false positive/negative fixtures allowed by policy, cancellation, multiple assets, app backgrounding, accessibility, and account switch.

## Gotchas

A classification is not identity, consent, or legal determination. Safety UI must not reveal private media to observers. Framework capabilities and policy may change.
