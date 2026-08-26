# third-party-api-monitoring

**Issue:** Monitoring external API dependencies for availability and latency changes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Your service degrades because a downstream API is slow or down. No visibility until users complain.

## Pattern / Solution
Instrument all outbound API calls as labeled histograms tracking error rate and p99 latency per external host. Subscribe to vendor status pages via StatusPage RSS feeds — alert Slack when vendor incidents open. Implement circuit breakers to fail fast when dependency is degraded. Use Datadog or Checkly for synthetic API monitoring.

## Gotchas
External API monitoring from your infrastructure only covers your vantage point. Rate limit errors (429) from vendors indicate your usage pattern needs adjustment. Implement retry with exponential backoff and jitter. Never retry non-idempotent operations without idempotency keys.

## Related
network-latency-monitoring, uptime-monitoring-patterns, synthetic-monitoring-setup, webhook-delivery-monitoring
