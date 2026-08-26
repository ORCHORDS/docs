# synthetic-monitoring-setup

**Issue:** Running scripted browser or API tests continuously in production to catch regressions before users do
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Reactive alerting only catches problems after users are impacted. Synthetic tests proactively validate critical user journeys.

## Pattern / Solution
Define synthetic tests for critical paths: login, checkout, API key auth, search. Use Datadog Synthetics, Checkly, or Playwright-based runners on a schedule every 1-5 minutes. Assert on HTTP status, response time thresholds, and body content. Store test scripts in version control. Alert on test failure and on performance regression.

## Gotchas
Synthetic tests generate noise in analytics — filter test traffic by User-Agent. Keep tests idempotent — do not create real orders. Rotate test accounts to avoid rate limiting. Multi-step browser tests are flaky if not written with explicit waits.

## Related
uptime-monitoring-patterns, blackbox-monitoring, datadog-synthetics, real-user-monitoring-rum
