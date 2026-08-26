# font-preloading

**Issue:** Fonts discovered late in the rendering pipeline delay text rendering
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Fonts are discovered when CSS is parsed, which is after HTML and CSS load. Preloading moves font fetch to immediately after HTML is parsed.

## Pattern / Solution
1. link rel=preload as=font type=font/woff2 href=/fonts/inter.woff2 crossorigin.\n2. Only preload fonts used in above-fold text.\n3. Preload the most important weight first; lazy-load other weights.\n4. Combine with font-display: optional to eliminate FOUT for preloaded fonts.\n5. Self-host fonts to avoid cross-origin latency.

## Gotchas
- crossorigin attribute is mandatory even for same-origin fonts.\n- Preloading fonts not used in the critical path wastes bandwidth.\n- Variable fonts allow preloading a single file for all weights/styles.

## Related
font-display-swap, font-subsetting, resource-hints-preload
