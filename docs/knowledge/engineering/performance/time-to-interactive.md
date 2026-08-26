# time-to-interactive

**Issue:** Time to Interactive is high; page appears loaded but is unresponsive
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
TTI measures when the main thread becomes reliably idle (no long tasks > 50ms for 5s) after FCP. High TTI means users click elements that do not respond.

## Pattern / Solution
1. Reduce JavaScript parse and execution time -- split bundles, lazy load non-critical code.\n2. Defer third-party scripts until after TTI.\n3. Move data fetching to the server to avoid client-side waterfalls.\n4. Prioritize loading and hydrating interactive components first.

## Gotchas
- TTI is a Lighthouse-only metric; no CrUX equivalent. Use INP as the field proxy.\n- Heavy frameworks without code splitting delay TTI significantly.\n- SSR without selective hydration delivers fast FCP but poor TTI if the full JS bundle must parse first.

## Related
inp-optimization, total-blocking-time, javascript-bundle-size, code-splitting-strategies
