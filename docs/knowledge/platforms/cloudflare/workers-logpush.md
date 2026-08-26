# workers-logpush

**Issue:** Configuring Logpush to export Worker logs and request data to external destinations
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare Logpush streams structured logs from Workers, HTTP requests, and other products to R2, S3, Datadog, Splunk, or any HTTPS endpoint. This is the production-grade alternative to Tail Workers for durable log storage.

## Pattern / Solution

```bash
# 1. Create a Logpush job via API
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/logpush/jobs" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "workers-logs-to-r2",
    "logpull_options": "fields=Event,EventTimestampMs,Outcome,Exceptions,Logs,ScriptName",
    "destination_conf": "r2://my-log-bucket/workers-logs?account-id=<ACCOUNT>&access-key-id=<AKI>&secret-access-key=<SAK>",
    "dataset": "workers_trace_events",
    "enabled": true
  }'

# 2. Enable Workers Trace Events for a specific script
# Done via the dashboard: Workers → your script → Logpush → Enable
```

```typescript
// Emit structured logs that appear in Logpush output
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // console.log output appears in workers_trace_events Logs field
    console.log(JSON.stringify({
      event: 'request',
      method: request.method,
      path: new URL(request.url).pathname,
      country: request.cf?.country,
    }));

    try {
      const result = await handleRequest(request, env);
      console.log(JSON.stringify({ event: 'success', status: result.status }));
      return result;
    } catch (err) {
      console.error(JSON.stringify({ event: 'error', message: String(err) }));
      return new Response('Internal Error', { status: 500 });
    }
  },
};
```

**Supported datasets:**
- `workers_trace_events` — Worker execution logs
- `http_requests` — Edge HTTP request logs
- `firewall_events` — WAF events
- `dns_logs` — DNS query logs

**Destination examples:**
```
r2://bucket-name/prefix?account-id=...&access-key-id=...&secret-access-key=...
s3://bucket-name/prefix?region=us-east-1&access-key-id=...&secret-access-key=...
https://logs.example.com/ingest   (HTTPS endpoint — Logpush will POST newline-delimited JSON)
datadog://...
```

## Gotchas
- Logpush delivers logs **asynchronously** in batches; expect 5–30 second delays.
- `workers_trace_events` requires the Worker to have **Trace Events** enabled per script — it is off by default.
- `console.log` output is included in the `Logs` field as an array of strings. Use JSON for structured logs.
- The `fields` param in `logpull_options` is comma-separated and case-sensitive.
- R2 Logpush requires an R2 API token (not a Cloudflare API token) — create one in R2 settings.
- Each Logpush job can target only one dataset; create separate jobs for different datasets.

## Related
- `workers-tail-workers.md`
- `workers-analytics-engine.md`
- `r2-best-practices.md`
