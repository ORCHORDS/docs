# Tail Workers for Real-Time Security Event Streaming

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You need real-time visibility into authentication failures, rate-limit hits, and anomalous request patterns across your Cloudflare Workers fleet without adding latency to the critical path.

## Context
Cloudflare Tail Workers receive a structured stream of log events from one or more producer Workers after each request completes. Because the tail handler runs asynchronously after the response is sent, it adds zero latency to end-user requests. Tail Workers are the correct place to implement SIEM forwarding, anomaly detection triggers, and security alerting for Workers-based APIs. The tail Worker sees request metadata, response status, console logs emitted by the producer, and any uncaught exceptions.

## Configuring the Tail Consumer
Bind the tail Worker to a producer Worker via `[[tail_consumers]]` in `wrangler.toml`. A single tail Worker can consume events from multiple producers.

```toml
# producer-api/wrangler.toml
name = "producer-api"
[[tail_consumers]]
service = "security-tail"
environment = "production"
```

```typescript
// security-tail/src/index.ts
export interface Env {
  SIEM_INGEST_URL: string;
  SIEM_TOKEN: string;
  ALERT_WEBHOOK_URL: string;
  SECURITY_KV: KVNamespace;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    const securityEvents: SecurityEvent[] = [];

    for (const event of events) {
      securityEvents.push(...extractSecurityEvents(event));
    }

    if (securityEvents.length === 0) return;

    await Promise.allSettled([
      forwardToSIEM(securityEvents, env),
      checkThresholdsAndAlert(securityEvents, env),
    ]);
  },
};
```

## Extracting Security-Relevant Events
Filter the full trace for events that signal authentication failures, authorization denials, WAF blocks, or anomalous inputs before forwarding, to avoid flooding your SIEM with noise.

```typescript
interface SecurityEvent {
  type: "auth_failure" | "rate_limit" | "waf_block" | "exception" | "suspicious";
  timestamp: number;
  rayId: string;
  method: string;
  path: string;
  statusCode: number | undefined;
  ip: string | undefined;
  userAgent: string | undefined;
  detail?: string;
}

function extractSecurityEvents(trace: TraceItem): SecurityEvent[] {
  const events: SecurityEvent[] = [];
  const req = trace.event?.request;
  if (!req) return events; // cron or queue events — skip

  const base = {
    timestamp: trace.eventTimestamp ?? Date.now(),
    rayId: trace.rayId ?? "",
    method: req.method,
    path: new URL(req.url).pathname,
    statusCode: trace.event?.response?.status,
    ip: req.headers["cf-connecting-ip"],
    userAgent: req.headers["user-agent"],
  } as const;

  // 401 / 403 signals authentication or authorization failure
  if (base.statusCode === 401 || base.statusCode === 403) {
    events.push({ ...base, type: "auth_failure" });
  }

  // Producer sets this header before returning 429
  if (req.headers["x-rate-limited"] === "1") {
    events.push({ ...base, type: "rate_limit" });
  }

  // Parse structured console logs emitted by the producer
  for (const log of trace.logs ?? []) {
    const msg = String(log.message ?? "");
    if (msg.includes("WAF_BLOCK")) {
      events.push({ ...base, type: "waf_block", detail: msg.slice(0, 512) });
    }
    if (msg.includes("SUSPICIOUS_INPUT")) {
      events.push({ ...base, type: "suspicious", detail: msg.slice(0, 512) });
    }
  }

  // Uncaught exceptions in the producer — potential crash-based exploits
  for (const ex of trace.exceptions ?? []) {
    events.push({
      ...base,
      type: "exception",
      detail: `${ex.name}: ${String(ex.message).slice(0, 256)}`,
    });
  }

  return events;
}
```

## Forwarding to a SIEM Endpoint
Send extracted events as newline-delimited JSON (NDJSON) to your SIEM or log aggregator over HTTPS. Store the ingest token as a Worker secret, never as a plain-text environment variable.

```typescript
async function forwardToSIEM(
  events: SecurityEvent[],
  env: Env
): Promise<void> {
  const body = events.map((e) => JSON.stringify(e)).join("\n");

  const response = await fetch(env.SIEM_INGEST_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-ndjson",
      Authorization: `Bearer ${env.SIEM_TOKEN}`,
    },
    body,
  });

  if (!response.ok) {
    // Do not re-throw — tail errors must never surface to users
    console.error(`[tail] SIEM forward failed: ${response.status}`);
  }
}
```

## Rolling Threshold Alerts via KV
Maintain per-IP rolling counters in KV to detect sustained brute-force or credential-stuffing campaigns and fire webhook alerts when thresholds are breached.

```typescript
async function checkThresholdsAndAlert(
  events: SecurityEvent[],
  env: Env
): Promise<void> {
  const authFailures = events.filter((e) => e.type === "auth_failure");

  for (const ev of authFailures) {
    if (!ev.ip) continue;

    const key = `thresh:auth_failure:${ev.ip}`;
    const raw = await env.SECURITY_KV.get(key);
    const count = raw ? parseInt(raw, 10) + 1 : 1;

    await env.SECURITY_KV.put(key, String(count), {
      expirationTtl: 300, // 5-minute sliding window
    });

    if (count === 10 || count === 50 || count === 100) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `SECURITY: IP ${ev.ip} hit ${count} auth failures in 5 min (ray=${ev.rayId})`,
          severity: count >= 50 ? "critical" : "high",
          ip: ev.ip,
          count,
        }),
      }).catch((err) =>
        console.error("[tail] alert webhook failed:", String(err))
      );
    }
  }
}
```

## Anti-patterns
- Performing heavy CPU work in the tail handler — it has a 1-second CPU budget per invocation
- Re-throwing errors from the tail handler — uncaught exceptions are silently dropped but consume budget
- Logging raw request bodies or Authorization header values — strip PII and secrets before emitting structured logs in the producer
- Forwarding every trace event to a paid SIEM without pre-filtering — inflates ingest costs by orders of magnitude
- Using tail Workers as the sole security control — they are observability tooling, not enforcement

## Gotchas
- `trace.event?.request` is absent for Cron Trigger and Queue Consumer invocations; always guard before accessing
- The `logs` array contains raw `console.log` output as an array — join elements with a space before string matching
- Tail Workers cannot read the response body from the producer, only the status code and headers
- Maximum tail event payload is 1 MB; very large responses or log volumes trigger truncation silently
- Tail Workers count toward your Workers request quota; budget accordingly on high-traffic routes

## Verification
1. Deploy both the producer and the tail Worker: `wrangler deploy` in each directory.
2. Call an auth-protected endpoint with an invalid token to produce a 401 response.
3. Run `wrangler tail security-tail --format=json` and confirm a `{"type":"auth_failure",...}` entry appears within a few seconds.
4. Trigger 10 rapid 401s from a single IP and verify the webhook fires with severity `high`.

## Related
- [Security Logging What to Log](security-logging-what-to-log.md)
- [Rate Limiting per User D1 Durable Objects](rate-limiting-per-user-d1-durable-objects.md)
- [Workers Environment Variable Hygiene](workers-environment-variable-hygiene.md)
- [Audit Log Security](audit-log-security.md)

## Sources
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/workers/runtime-apis/tail-event/
- https://developers.cloudflare.com/workers/configuration/bindings/
- https://developers.cloudflare.com/workers/observability/logging/workers-trace-events/
