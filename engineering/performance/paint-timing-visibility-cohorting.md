# Paint Timing visibility cohorting

**Issue:** First Paint and First Contentful Paint describe early rendering, but hidden starts, restored pages, prerendering, and incomplete browser support can make apparently fast samples incomparable. Aggregating them without lifecycle context biases performance decisions.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Observe buffered `paint` entries early and preserve the standardized entry name rather than assuming order. Record initial visibility, activation/restoration context, navigation type, browser/version, and time origin. Exclude or separately cohort pages hidden before the relevant paint and prerendered pages whose user-visible activation differs from document start.

Keep FCP distinct from LCP and application-ready marks. Missing entries remain missing, not zero. Apply sampling and strip URL/user data before export.

## Verification

Test cold/warm navigation, hidden tab start, prerender activation, BFCache restore, server/client rendering, web fonts, images, unsupported browsers, delayed observer registration, and buffer clearing. Compare RUM cohorts with controlled traces.

## Gotchas

FCP reports the first qualifying content, not useful or complete content. Paint timing is relative to the document time origin; cross-navigation comparisons require lifecycle metadata.

## Sources

- W3C Web Performance WG, [Paint Timing](https://www.w3.org/TR/paint-timing/)
- W3C Web Performance WG, [Page Visibility Level 2](https://www.w3.org/TR/page-visibility-2/)
