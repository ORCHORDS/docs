# cloudflare-analytics-engine

**Issue:** Storing and querying time-series analytics in Cloudflare Workers using Analytics Engine
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Need cheap, scalable event storage directly from Workers without routing through external services. Analytics Engine is a write-optimized time-series store accessible via SQL API.

## Pattern / Solution
Bind dataset in wrangler.toml: analytics_engine_datasets = [{binding = 'AE', dataset = 'prod_events'}]. Write from Worker: env.AE.writeDataPoint({blobs: ['event_type'], doubles: [latency_ms], indexes: ['tenant_id']}). Query via SQL API: SELECT blob1, avg(double1) FROM prod_events WHERE timestamp > NOW() - INTERVAL '1' HOUR GROUP BY blob1.

## Gotchas
Max 20 blobs and 20 doubles per data point. Indexes are for partitioning — choose high-cardinality fields carefully. Data is eventually consistent. Free tier has row limits.

## Related
cloudflare-workers-analytics, cloudflare-logpush-setup, metrics-vs-logs-vs-traces
