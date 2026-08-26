# cloudflare-workers-analytics

**Issue:** Monitoring Cloudflare Workers performance and traffic via built-in analytics
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Need visibility into Worker invocation counts, CPU time, error rates, and subrequest latency without external tooling.

## Pattern / Solution
Access Workers Analytics via Cloudflare dashboard > Workers and Pages > your worker > Analytics tab. View request volume, error rate, CPU time (p50/p99). For programmatic access use GraphQL Analytics API querying workersInvocationsAdaptive with filters. Pipe to Grafana using Cloudflare Grafana datasource plugin.

## Gotchas
CPU time and wall time differ — wall time includes I/O waits. Free plans show aggregated data with limited granularity. Real-time logs require Logpush or the Workers real-time logs API.

## Related
cloudflare-analytics-engine, cloudflare-logpush-setup, worker-cpu-monitoring
