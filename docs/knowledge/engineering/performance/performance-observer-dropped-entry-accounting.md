# PerformanceObserver dropped-entry accounting

**Issue:** A RUM pipeline assumes every performance entry reached its observer even when browser buffers dropped entries under load.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer callback option; feature-detect

Performance Timeline provides dropped-entry information in observer callback options where supported. Treat drops as telemetry-integrity loss: record a bounded counter and avoid drawing complete-distribution conclusions from that sample.

**Source:** [W3C Performance Timeline](https://www.w3.org/TR/performance-timeline/)

## Controls

- feature-detect callback metadata;
- increment a capped per-entry-type/session loss counter;
- keep observer callback work minimal;
- register early and use buffered delivery where appropriate;
- sample/export loss without retry loops or synthetic replacement;
- mark affected metric batches incomplete.

## Verification

Generate buffer pressure, late observer registration, long callback work, navigation/termination, supported/unsupported browsers, and multiple observers. Confirm dropped data is never fabricated or silently treated as zero.

## Gotchas

A drop count may not identify which entries vanished. Increasing buffers can increase memory and does not fix slow callbacks. Missing drop metadata does not prove complete delivery.
