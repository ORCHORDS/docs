# cloudflare-logpush-setup

**Issue:** Streaming Cloudflare logs to external storage or SIEM via Logpush
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Need raw HTTP request logs, Workers logs, or Firewall events delivered continuously to S3, R2, Datadog, or Splunk for long-term analysis.

## Pattern / Solution
Create a Logpush job via dashboard (Analytics > Logs > Logpush) or API. Select dataset (http_requests, workers_trace_events, firewall_events). Configure destination with credentials. Set fields and filters. Jobs deliver logs in batches every 30 seconds in newline-delimited JSON.

## Gotchas
Logpush requires a paid plan for HTTP request logs. Workers Trace Events require Workers Paid plan. R2 destination is cheapest for archival. Each job pushes one dataset — create separate jobs per dataset.

## Related
cloudflare-workers-analytics, cloudflare-analytics-engine, log-retention-policies
