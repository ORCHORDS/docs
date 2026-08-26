# render-blocking-resources

**Issue:** CSS and JS files delay first paint
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
By default, CSS blocks rendering and synchronous JS blocks both HTML parsing and rendering. Every render-blocking resource adds at least one network round trip before the browser paints.

## Pattern / Solution
1. Audit with Lighthouse Eliminate render-blocking resources opportunity.\n2. Add defer to all non-critical script tags.\n3. Split CSS: inline critical styles, load non-critical with media=print trick or async load.\n4. Preload critical CSS with link rel=preload as=style.\n5. Remove or defer third-party scripts that arrive in head.

## Gotchas
- script type=module is deferred by default -- no need to add defer.\n- Some CSS frameworks include unused rules; purge with PurgeCSS or Tailwind's JIT.\n- Fonts declared in CSS trigger additional blocking requests; preload them explicitly.

## Related
critical-rendering-path, javascript-bundle-size, above-fold-optimization, font-preloading
