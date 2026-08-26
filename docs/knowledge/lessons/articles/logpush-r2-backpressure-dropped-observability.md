# Incident Report: Logpush R2 Backpressure Caused Dropped Observability Data

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production
- **Severity:** P2 — observability data loss, no user-facing impact
- **Duration:** 6 hours 44 minutes

---

## Symptom

During a high-traffic event, the platform's observability pipeline went dark. Cloudflare Logpush, configured to deliver Workers trace logs to an R2 bucket, stopped delivering data for 6 hours and 44 minutes. When delivery resumed, 31% of logs from the affected window were permanently lost — not delayed, but dropped. The on-call engineer discovered the gap the following morning when querying the log store for an unrelated incident investigation and finding a 6-hour hole.

No alert fired during the log loss window because the alerting system itself depended on the log pipeline.

---

## Context

Cloudflare Logpush is a platform feature that streams structured log data (Workers traces, HTTP request logs, Firewall events) to a destination. The platform had configured Logpush to deliver Workers trace events to an R2 bucket in 5-minute batches. A secondary pipeline read from R2 and indexed the logs into a queryable store (Elasticsearch running on Fly.io).

R2, like S3, has eventual-consistency semantics and supports concurrent writes, but it imposes rate limits on write operations per bucket. During the high-traffic event, Workers trace volume increased 18x and Logpush attempted to write many more objects per minute than the R2 bucket could accept. R2 returned 429 (Too Many Requests) responses to Logpush. Logpush's backpressure handling at the time dropped logs that could not be delivered after several retries, rather than buffering them.

---

## Timeline

| UTC | Event |
|---|---|
| 18:12 | Traffic spike begins (promotional campaign launch) |
| 18:14 | Logpush write rate to R2 exceeds bucket rate limit |
| 18:14 | R2 begins returning 429 to Logpush |
| 18:15 | Logpush begins dropping logs after retry exhaustion |
| 18:15 – 00:59 | 6h 44m of partial/complete log loss |
| 01:02 | Traffic normalises; R2 write rate drops below limit |
| 01:04 | Logpush resumes normal delivery |
| 08:47 next day | On-call engineer discovers 6-hour gap during unrelated investigation |
| 09:15 | Incident declared; root cause identified |

---

## Root Cause Analysis

### Primary: R2 Bucket Write Rate Limit Exceeded Under Spike

R2 imposes a maximum write operations per second per bucket. Under the 18x traffic spike, the volume of Workers trace events exceeded this limit. Logpush, which batches events and writes one object per batch to R2, hit the rate limit and received 429 responses.

The platform's R2 write rate was not monitored. There was no alert configured for R2 write errors or Logpush delivery failures.

### Contributing: Logpush Drop Behaviour Under Retry Exhaustion

Logpush's retry policy at the time retried failed writes with backoff but dropped events that could not be delivered within the retry window. This is documented Logpush behaviour — Logpush is designed for "best-effort" delivery, not guaranteed delivery. The platform had not read or accounted for this in the observability architecture.

### Contributing: Circular Dependency Between Alerting and Log Pipeline

The alerting system used rules that evaluated Workers trace data. When the trace data stopped flowing, the alerting rules had no data to evaluate — they evaluated as "no data," which many alerting systems treat as "no alert." The log pipeline outage was invisible to the very system designed to detect outages.

### Contributing: No Independent Health Check for Logpush

The platform had no independent health check that verified Logpush was writing to R2 at the expected rate. A simple metric — "R2 objects written to observability bucket per 5 minutes" — would have detected the gap within 5 minutes of it starting.

---

## Technical Sections

### 1. Logpush Delivery Guarantees and Backpressure Model

Cloudflare Logpush provides best-effort delivery. The SLA documentation states that logs may be dropped if the destination is unavailable or rate-limiting. This is not a defect — it is the documented behaviour — but it is frequently misunderstood by teams who treat Logpush as a reliable message delivery system.

Key properties:
- Logpush retries failed deliveries but has a finite retry budget
- After retry exhaustion, logs are dropped and cannot be recovered
- There is no Logpush dead-letter mechanism
- Logpush does not buffer indefinitely; it is a streaming push system, not a durable queue

Teams that need guaranteed log delivery must either:
- Accept best-effort delivery and design observability to tolerate gaps
- Use an alternative delivery path with guaranteed semantics (e.g., writing to Cloudflare Queues from Workers and consuming to a durable store)
- Configure Logpush to a highly available, high-throughput destination (Logpush supports R2, S3, GCS, HTTP endpoint, Sumo Logic, Splunk, Datadog, New Relic, and others)

### 2. R2 Bucket Rate Limits and Sharding

R2 write rate limits apply per bucket. The limit is not publicly documented with a specific number, but in practice:
- High-throughput log delivery should use multiple R2 buckets to spread write load
- Prefix sharding within a single bucket does not bypass the per-bucket rate limit; the limit is on operations per bucket, not per prefix

The correct architecture for high-throughput Logpush to R2 uses multiple buckets and a Logpush job per bucket, with each job delivering a subset of Workers (or a subset of data centres). This distributes write operations across multiple per-bucket limits.

Example: four Logpush jobs, each targeting a different R2 bucket, each scoped to a subset of Cloudflare data centres via a Logpush filter. Each bucket receives 1/4 of the total write load.

```
Logpush Job 1 → filter: colo in ["SJC","LAX","SEA"] → r2://logs-us-west
Logpush Job 2 → filter: colo in ["DFW","ORD","IAD"] → r2://logs-us-east
Logpush Job 3 → filter: colo in ["LHR","AMS","FRA"] → r2://logs-eu
Logpush Job 4 → filter: colo in ["NRT","SIN","SYD"] → r2://logs-apac
```

This is operationally more complex but removes the single-bucket bottleneck.

### 3. Breaking the Circular Alerting Dependency

Any alerting system that depends on the same data pipeline it is monitoring has a circular dependency — the alerting goes blind precisely when the pipeline fails. This is a structural problem that must be solved architecturally.

**Pattern: Independent delivery path for control-plane metrics.**

Critical health metrics (log ingestion rate, pipeline throughput, error counts) should be delivered via a separate pipeline from the log data itself. If the log pipeline fails, the control-plane metrics pipeline continues to function independently.

For the Cloudflare Workers platform, this means:
- Application logs: Logpush → R2 → Elasticsearch (primary pipeline)
- Control-plane metrics: Workers Analytics Engine → GraphQL Analytics API → alerting system

Workers Analytics Engine writes to Cloudflare's internal time-series infrastructure, which is independent of Logpush and R2. It cannot be interrupted by an R2 rate-limit event. Use it to track:

```ts
// Written from within each Worker invocation
env.ANALYTICS.writeDataPoint({
  blobs: ['request_completed'],
  doubles: [1],
  indexes: ['control_plane'],
});
```

Alert on control-plane metric count dropping below expected rate. This alert fires even if Logpush is down.

### 4. Detecting Logpush Gaps

R2 itself can be used to detect Logpush gaps:

```ts
// Cron Trigger Worker — runs every 5 minutes
export default {
  async scheduled(event, env) {
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000);
    const prefix = `logs/${fiveMinutesAgo.toISOString().slice(0, 15)}`; // e.g. "logs/2026-08-22T18"

    const list = await env.LOGS_BUCKET.list({ prefix, limit: 1 });
    if (list.objects.length === 0) {
      // No objects written in the last 5-minute window — potential Logpush gap
      await env.ALERT_QUEUE.send({
        type: 'logpush_gap_detected',
        window: prefix,
        ts: Date.now(),
      });
    }
  }
};
```

This health-check Worker is independent of the log pipeline it monitors. It runs on Cloudflare's Cron Trigger infrastructure, which is separate from Logpush and R2 object delivery. A gap in R2 object creation is detected within the next 5-minute cron window.

### 5. Alternative: Workers Analytics Engine as Primary Observability Sink

For teams that need guaranteed delivery of trace data, Cloudflare Workers Analytics Engine offers an alternative to Logpush with different trade-offs:

| Property | Logpush | Analytics Engine |
|---|---|---|
| Delivery guarantee | Best-effort | Higher (Cloudflare internal) |
| Query interface | External (your destination) | GraphQL Analytics API |
| Latency to query | Minutes (depends on pipeline) | ~1 minute |
| Data retention | You control (in destination) | 90 days |
| Rate limit | Destination-dependent | 25 data points/request |
| Cost | Logpush: free; destination: yours | Included in Workers paid plan |
| Suitable for | Rich logs, full traces | Aggregated metrics, counts |

Analytics Engine is appropriate for aggregate metrics (requests per minute, error rate, latency percentiles). It is not appropriate for full-text log search or reproducing individual trace records. A combined approach — Analytics Engine for control-plane metrics and alerting, Logpush for full trace archival — addresses both needs.

### 6. Runbook: Responding to a Logpush Gap

When a Logpush gap is detected:

1. **Assess scope.** Query R2 for the affected time window's objects. Compare expected object count (based on typical 5-minute batch volume) with actual.
2. **Check R2 metrics.** Cloudflare dashboard → R2 → Metrics → write errors in the affected window. Confirm whether 429s were returned.
3. **Check Logpush job status.** Dashboard → Logpush → verify job is enabled and has no "paused" or "error" state.
4. **Quantify data loss.** Count of missing objects × typical events per object = estimated events lost. This cannot be recovered from Logpush.
5. **Assess impact on active incidents.** If the gap covers an open incident investigation window, explicitly note that log data is incomplete and increase reliance on control-plane metrics.
6. **Apply mitigation.** If gap is ongoing: temporarily reduce Logpush field set to reduce write volume, or enable Logpush filtering to reduce event volume. If gap is resolved: no recovery action possible for dropped logs.
7. **Post-incident.** Add R2 write error alert; implement bucket sharding if volume warrants.

---

## Anti-Patterns

- **Treating Logpush as a guaranteed delivery system.** It is not. Design observability architectures that degrade gracefully when Logpush drops data, rather than assuming 100% delivery.
- **Using a single R2 bucket for all Logpush delivery at scale.** A single bucket's write rate limit is a hard ceiling. High-traffic platforms must shard across multiple buckets.
- **Alerting only on data from the pipeline being monitored.** Any critical alert must have an independent delivery path. Use Analytics Engine, an external uptime monitor, or a heartbeat mechanism separate from the primary pipeline.
- **No health-check for the log pipeline itself.** The log pipeline is infrastructure that can fail. Treat it like any other infrastructure: monitor its health independently.
- **Confusing "no data" with "no issue" in alerting systems.** Configure alerting rules to fire on "no data" as a separate alert condition. A metric going silent is often a failure, not a sign of health.

---

## Gotchas

- Cloudflare does not provide a "Logpush delivery confirmation" API. Once a batch is delivered to R2, Logpush considers it done. There is no acknowledgement loop back to Logpush.
- R2 list operations are limited to 1,000 objects per call. Detecting gaps by listing R2 objects works at low volume; at high volume the list will be paginated and the health check Worker must handle pagination.
- The 5-minute Logpush batch interval means the minimum gap detection window is 5 minutes. Gaps shorter than 5 minutes may not be detectable via the R2 object count method.
- Logpush fields can be customised. If the field set is very large, each log event serialises to a larger object, increasing write volume and contributing to rate limit pressure. Reduce the field set to the minimum required for your use cases.
- Workers Analytics Engine has a limit of 25 data points per `writeDataPoint()` call and a maximum of 1,000 data points per second per account. High-traffic platforms should sample Analytics Engine writes rather than writing on every request.

---

## Verification

Post-incident changes verified on 2026-08-19:

1. R2 bucket sharding implemented: 4 Logpush jobs, 4 buckets, each receiving approximately 1/4 of trace volume. Under simulated 20x traffic, no 429 errors observed.
2. Cron Trigger health-check Worker deployed: confirmed it fires an alert when no R2 objects are written in a 5-minute window (tested by temporarily disabling Logpush job).
3. Analytics Engine control-plane metrics operational: alert configured for request rate dropping >50% unexpectedly, using Analytics Engine as data source (independent of Logpush).
4. Alerting system updated: "no data" conditions now fire as distinct alerts rather than silently resolving.

---

## Related

- `observability-first-engineering-culture.md`
- `monitoring-blackout-during-incident.md`
- `alert-fatigue-masks-real-outages-2026.md`
- `telemetry-sampling-must-retain-rare-failures.md`
- `cloudflare-storage-primitive-selection.md`
- `log-correlation-ids-from-day-one.md`
- `incident-timeline-capture-must-be-automatic-2026.md`

---

## Sources

- Cloudflare Logpush documentation: https://developers.cloudflare.com/logs/logpush/
- Cloudflare R2 documentation: https://developers.cloudflare.com/r2/
- Workers Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Logpush best practices: https://developers.cloudflare.com/logs/best-practices/
