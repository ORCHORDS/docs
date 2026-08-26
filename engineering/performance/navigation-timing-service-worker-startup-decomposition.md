# Navigation Timing service-worker startup decomposition

**Issue:** Real-user monitoring labels fetchStart minus workerStart as “service-worker execution time” and compares it directly with network latency. Unsupported entries, already-running workers, activation, routing, and browser timing rules make that interpretation inaccurate and can send optimization work to the wrong layer.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published using current Navigation Timing fields

## Problem and applicability

PerformanceNavigationTiming exposes workerStart and fetchStart for navigation timing. When a service worker participates, workerStart marks the relevant beginning of worker startup/activation processing defined by the specification, while fetchStart marks the point associated with dispatching the fetch event or beginning the network fetch path.

Their difference is a diagnostic interval around service-worker readiness before fetch handling. It is not pure CPU time, a guaranteed worker boot measurement, or the fetch handler's total duration.

## Controls and implementation

1. Read the navigation entry through performance.getEntriesByType("navigation") and version the telemetry schema.
2. Treat workerStart equal to zero as no attributable service-worker start for this navigation. Keep that cohort separate rather than coercing it to navigationStart.
3. Require finite monotonic values and fetchStart greater than or equal to workerStart before deriving the interval. Reject malformed or privacy-reduced samples.
4. Segment by navigation type, service-worker controller/version where safely available, browser version, warm versus cold process proxy, and deployment cohort. Do not mix reload, back-forward, prerender, and ordinary navigate traffic blindly.
5. Interpret the derived interval as startup/activation-to-fetch-dispatch context. Use service-worker logs, DevTools traces, and controlled tests to determine whether installation/activation, script evaluation, routing, or scheduling is responsible.
6. Measure actual fetch-handler and network/cache outcomes separately with resource timing, server timing, and handler instrumentation where available.
7. Keep raw timestamps and the derivation version so future specification changes can be reprocessed. Apply privacy and sampling limits to URL and worker-version metadata.
8. Compare distributions and percentiles with sample sizes, not a single average or a fabricated universal threshold.

## Verification

Test no service worker, first install, waiting-to-active transition, cold worker, already-running worker, navigation preload, cache response, network response, worker exception/fallback, controller change, update, reload, back-forward, and mixed browser support.

Correlate RUM with controlled browser traces. Assert unsupported/zero values are excluded from the derived interval but remain visible as a separate population.

## Gotchas

- The interval can include activation or startup work and scheduling; it is not just JavaScript evaluation.
- fetchStart is a boundary timestamp, not response start or network completion.
- A fast startup interval can still precede a slow fetch handler.
- Do not depend on draft-only fields absent from the current published interface.

## Official sources

- [W3C — Navigation Timing Level 2](https://www.w3.org/TR/navigation-timing-2/)
- [W3C — Service Workers](https://www.w3.org/TR/service-workers/)
