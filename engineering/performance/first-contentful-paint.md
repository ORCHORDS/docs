# first-contentful-paint

**Issue:** First Contentful Paint is slow, delaying perceived load
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
FCP marks when the browser renders the first bit of DOM content (text, image, SVG). A fast FCP (< 1.8s) reassures users the page is loading. Heavily influenced by TTFB and render-blocking resources.

## Pattern / Solution
1. Eliminate render-blocking CSS; inline critical styles, defer the rest.\n2. Reduce server response time (TTFB).\n3. Preconnect to font/CDN origins early.\n4. Avoid large synchronous scripts in head.\n5. Use a lightweight skeleton or placeholder to paint something visible immediately.

## Gotchas
- FCP fires on any painted content including background color; a white flash before real content still scores poorly.\n- Server-side rendering improves FCP over CSR but requires streaming to maximize benefit.\n- Lighthouse FCP is lab data; CrUX FCP is field data -- both matter.

## Related
ttfb-optimization, render-blocking-resources, critical-rendering-path, resource-hints-preconnect
