# User-Agent-Specific Memory Regression Sampling

**Issue:** Heap-only measurements miss browser-managed memory, but one user-agent memory sample is noisy and incomparable across browsers or versions.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use `performance.measureUserAgentSpecificMemory()` only in a secure, cross-origin-isolated context and after feature detection. Sample periodically at randomized intervals and around stable product milestones, not on every interaction. Compare distributions and within-browser/version deltas, never absolute budgets shared across engines.

Record a coarse scenario, build, browser version, elapsed session time, and total bytes; collect breakdown or attribution only after privacy review and tolerate implementation-dependent shapes. Establish regression thresholds from repeated baseline runs and confirm candidates with heap snapshots or allocation profiling.

Cross-origin isolation requires appropriate COOP/COEP deployment and compatible subresources. Do not weaken or unexpectedly impose isolation solely for telemetry without reviewing integrations.

## Verification

Run repeated clean sessions, known leak fixtures, long-lived navigation, iframe/worker scenarios, memory pressure, background/foreground, and unsupported browsers. Confirm sampling does not retain references, block interaction, or send identifiers. Reproduce any alert with profiling before fixing.

## Gotchas

Garbage collection timing creates variance. Values cannot be compared across browsers or browser releases. The API is limited and may reject if security requirements are unmet.

## Sources

- [MDN measureUserAgentSpecificMemory](https://developer.mozilla.org/en-US/docs/Web/API/Performance/measureUserAgentSpecificMemory)
- [WICG memory measurement](https://wicg.github.io/performance-measure-memory/)
