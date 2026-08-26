# Performance eventCounts interaction-volume diagnostics

**Issue:** A page accumulates excessive event activity but telemetry samples only slow interactions, missing repeated input patterns that amplify work.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer/limited API; feature-detect

The Event Timing specification exposes `performance.eventCounts`, a map-like count of dispatched event types. Use coarse deltas at stable milestones as diagnostic context, not user-behavior surveillance.

**Source:** [W3C Event Timing — eventCounts](https://w3c.github.io/event-timing/#dom-performance-eventcounts)

## Controls

- feature-detect and allowlist coarse event types;
- record deltas, route/release, and sampling window;
- exclude text, targets, coordinates, and identifiers;
- sample outside interaction-critical callbacks;
- correlate with INP/long tasks without assuming causation.

## Verification

Test supported/unsupported engines, navigation boundaries, SPA route changes, synthetic events, long sessions, backgrounding, and sampling reset logic.

## Gotchas

Counts do not measure handler cost or user intent. Browser inclusion rules may evolve. High counts can be legitimate and must be reproduced before optimization.
