# Resource Timing Critical-CH restart attribution

**Issue:** A navigation pays an extra restart for critical client hints, but RUM attributes the delay to ordinary server response time.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** experimental/newer field; feature-detect

Newer Navigation/Resource Timing work exposes `criticalCHRestart` to identify when a request restarted because required client hints were not present initially. Preserve the raw timestamp and compare affected versus unaffected navigations.

**Sources:** [W3C Resource Timing](https://w3c.github.io/resource-timing/) · [W3C Navigation Timing](https://w3c.github.io/navigation-timing/)

## Controls

- feature-detect and retain unsupported/zero as separate cohorts;
- send Critical-CH only for hints essential to the first response;
- align Accept-CH, permissions policy, cache variation, and CDN behavior;
- avoid high-entropy hints without a justified privacy contract;
- version server header changes beside RUM formulas.

## Verification

Test first visit, repeat visit, cleared client-hint state, missing/present hints, redirects, CDN cache variants, unsupported browsers, and permissions restrictions. Confirm headers do not create restart loops or cache fragmentation.

## Gotchas

Zero can mean no restart or unavailable data. A restart is not automatically a regression if it enables a required representation, but its latency and privacy cost must be measured. Client hints are not stable identity.
