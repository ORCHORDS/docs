# Element Timing hero attribution

**Issue:** A team tracks LCP but cannot measure when a specific hero image or text element rendered across page variants, so component regressions are hidden in aggregate metrics.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** limited/experimental availability; use as supplemental telemetry

The Element Timing API reports render timing for explicitly identified eligible elements. Use an `elementtiming` identifier and observe `element` performance entries after feature detection. It supplements Core Web Vitals; it is not a replacement for LCP.

**Source:** [W3C Element Timing specification](https://w3c.github.io/element-timing/)

## Controls

- annotate only a small allowlist of meaningful owned elements;
- collect buffered entries early and cap records per page;
- use stable low-cardinality identifiers rather than user-derived values;
- respect cross-origin image timing requirements and redaction;
- correlate with route, release, LCP, and visibility without transmitting text content or URLs.

## Verification

Test cached/network images, text, lazy loading, hidden elements, responsive variants, cross-origin resources with/without permission, SPA navigation, and unsupported browsers. Compare field samples with browser traces.

## Gotchas

Eligibility and available fields vary. An element can render more than once, and the reported timestamp does not prove the user noticed it. Instrumentation itself must remain lightweight.
