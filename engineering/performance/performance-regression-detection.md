# performance-regression-detection

**Issue:** Performance regressions merged without detection
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without automated checks, performance regressions are discovered after deployment when users complain or metrics degrade. CI-integrated performance testing catches regressions at PR review time.

## Pattern / Solution
1. Run Lighthouse CI on every PR; compare against base branch scores.\n2. Track bundle size changes with bundlesize or size-limit libraries.\n3. Set up CrUX API monitoring with daily alerts on metric threshold crossings.\n4. Use synthetic monitoring (Datadog Synthetics, SpeedCurve) on a schedule.\n5. Establish a performance review step in your release process for major features.

## Gotchas
- Single Lighthouse runs vary +/- 5-10 points; use median of 3 runs to reduce noise.\n- Lab regressions don't always show in field data immediately; the CrUX 28-day window smooths changes.\n- Framework upgrades often change bundle size; budget for upgrade costs.

## Related
performance-budget-setup, lighthouse-scoring, crux-field-data, pagespeed-insights-api
