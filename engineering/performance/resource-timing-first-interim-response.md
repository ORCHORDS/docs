# Resource Timing first interim response attribution

**Issue:** A navigation receives an interim HTTP response such as 103 Early Hints, but telemetry cannot separate the interim response arrival from the final response.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer/experimental field; feature-detect

Resource Timing defines `firstInterimResponseStart` for the first interim response. Preserve it with `requestStart`, `responseStart`, and final milestones to measure whether interim delivery creates useful lead time.

**Source:** [W3C Resource Timing](https://w3c.github.io/resource-timing/#dom-performanceresourcetiming-firstinterimresponsestart)

## Controls

- feature-detect and preserve an unsupported bucket;
- record raw timestamps before deriving lead time;
- correlate with response headers, resource discovery, LCP, protocol, and release;
- keep URLs sanitized and records sampled;
- make correctness independent of interim responses.

## Verification

Test no interim response, one/multiple interim responses, 103 followed by final response, redirect, cache, service worker, cross-origin redaction, and unsupported browsers. Compare RUM with controlled network traces.

## Gotchas

A nonzero timestamp does not prove hinted resources were useful or nonduplicated. Intermediaries may suppress interim responses. Do not subtract absent/zero values as if they were timestamps.
