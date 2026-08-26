# Performance time-origin cross-realm correlation

**Issue:** Performance timestamps are monotonic offsets from a realm's time origin, while logs and traces often use wall-clock time. Comparing offsets from windows, workers, servers, or navigations directly produces impossible ordering and negative latency.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Carry each sample's realm identifier and `performance.timeOrigin` with its monotonic timestamp. Convert to an approximate epoch only at an explicit correlation boundary, preserving the original pair. For window/worker correlation, exchange calibration messages and quantify message delay instead of assuming identical origins. Treat server clock correlation as a separate, uncertainty-bearing operation.

Use monotonic durations for in-realm latency and wall-clock values only for coarse ordering across systems. Reset correlation on navigation, worker restart, BFCache/lifecycle changes where applicable, and browser process changes. Apply privacy-aware precision and never turn clock offsets into fingerprints.

## Verification

Test dedicated/shared/service workers, reload/navigation, BFCache, sleep/resume, system clock changes, timezone changes, multiple tabs, delayed messages, server clock skew, and reduced timer precision. Assert duration calculations never mix realms without calibration and retain an uncertainty field.

## Gotchas

`timeOrigin + now()` approximates epoch time but does not create a globally synchronized clock. Wall clocks can jump; monotonic clocks and origins are realm/lifecycle scoped. Browser privacy controls may reduce precision.

## Sources

- W3C Web Performance Working Group, [High Resolution Time](https://www.w3.org/TR/hr-time/)
- W3C Web Performance Working Group, [Performance Timeline](https://www.w3.org/TR/performance-timeline/)
