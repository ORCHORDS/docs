# fid-elimination

**Issue:** First Input Delay (legacy metric) exceeded 100ms
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
FID measured the delay from the first user interaction to when the browser began processing event handlers. Retired in favor of INP in March 2024, but historical CrUX data still references it.

## Pattern / Solution
1. Reduce main-thread blocking during page load (parse + execute JS).\n2. Split bundles so critical JS loads first; defer everything else.\n3. Use code splitting and dynamic imports for non-critical features.\n4. Leverage browser idle time via requestIdleCallback for initialization.

## Gotchas
- FID only captured the first interaction; it missed slow subsequent interactions that INP now catches.\n- Sites with good FID sometimes have poor INP -- do not conflate the two.\n- Legacy Lighthouse scores still report FID for audits run against older profiles.

## Related
inp-optimization, long-task-detection, javascript-bundle-size, code-splitting-strategies
