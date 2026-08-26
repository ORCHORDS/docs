# uptime-monitoring-patterns

**Issue:** Designing reliable uptime checks that distinguish real outages from transient failures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Simple ping monitors generate false alerts on network blips. Need patterns that confirm genuine unavailability before paging.

## Pattern / Solution
Use multi-region probes (at least 3 regions); only alert when 2+ regions agree service is down. Check every 30-60 seconds. Use TCP/HTTP checks with assertions on status code and response body. Implement a confirmation window: fire alert only if N consecutive checks fail. Track uptime percent per rolling 30-day window for SLA reporting.

## Gotchas
DNS TTL can cause region probes to hit different IPs. CDN edge caches may return 200 from cache even when origin is down — probe origin directly or use a cache-busting query param. Check response time too.

## Related
synthetic-monitoring-setup, blackbox-monitoring, health-check-endpoint-design, sli-slo-sla-definitions
