# Workers-Based Active Health Checking with KV Backend

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Workers application proxies traffic to multiple downstream service endpoints, and you need to automatically detect and bypass unhealthy backends without relying on Cloudflare's paid Load Balancing product. When all backends are unavailable you want clients to receive a clear `Retry-After` response, and on-call engineers to receive a Slack alert when backend health state transitions occur.

---

## Context
Cloudflare Workers' `scheduled()` cron handler can ping service endpoints on a fixed interval (e.g., every minute) and persist the result — status, latency, and timestamp — to a KV namespace. The main `fetch()` handler reads that KV health state before selecting a backend, skipping any that are marked unhealthy. Because KV reads are globally fast and the health data is written on a cron cadence, request-path overhead is negligible. State-transition events (healthy → unhealthy, unhealthy → healthy) are pushed to a Cloudflare Queue, and a separate consumer Worker forwards the alert to Slack. This pattern gives you active health checking with alerting at zero additional licensing cost.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "load-balancer"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "HEALTH_KV"
id = "<your-kv-namespace-id>"

[[queues.producers]]
binding = "ALERT_QUEUE"
queue = "health-alerts"

[[queues.consumers]]
queue = "health-alerts"
max_batch_size = 10
max_batch_timeout = 5

[triggers]
crons = ["* * * * *"]

[vars]
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/XXX/YYY/ZZZ"
```

## Section 2 — Implementation

```typescript
// src/index.ts
export interface Env {
  HEALTH_KV: KVNamespace;
  ALERT_QUEUE: Queue;
  SLACK_WEBHOOK_URL: string;
}

const BACKENDS = [
  "https://api-1.internal.example.com",
  "https://api-2.internal.example.com",
  "https://api-3.internal.example.com",
];

const HEALTH_TIMEOUT_MS = 3000;
const UNHEALTHY_SCORE_THRESHOLD = 30;

interface HealthRecord {
  status: "healthy" | "unhealthy";
  latencyMs: number;
  ts: number;
  httpStatus?: number;
}

async function pingBackend(url: string): Promise<HealthRecord> {
  const start = Date.now();
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    const res = await fetch(`${url}/health`, {
      method: "GET",
      signal: controller.signal,
      headers: { "User-Agent": "orchords-healthcheck/1.0" },
    });
    clearTimeout(timeoutId);
    const latencyMs = Date.now() - start;
    const status = res.ok ? "healthy" : "unhealthy";
    return { status, latencyMs, ts: Date.now(), httpStatus: res.status };
  } catch {
    return { status: "unhealthy", latencyMs: Date.now() - start, ts: Date.now() };
  }
}

async function getHealthyBackends(env: Env): Promise<string[]> {
  const results = await Promise.all(
    BACKENDS.map(async (backend) => {
      const raw = await env.HEALTH_KV.get(`health:${backend}`);
      if (!raw) return backend; // assume healthy if no data yet
      const record: HealthRecord = JSON.parse(raw);
      // Treat records older than 3 minutes as stale — skip backend
      if (Date.now() - record.ts > 3 * 60 * 1000) return null;
      return record.status === "healthy" ? backend : null;
    })
  );
  return results.filter((b): b is string => b !== null);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const healthyBackends = await getHealthyBackends(env);

    if (healthyBackends.length === 0) {
      return new Response("Service Unavailable — all backends unhealthy", {
        status: 503,
        headers: {
          "Retry-After": "30",
          "Content-Type": "text/plain",
        },
      });
    }

    // Simple round-robin via request URL hash
    const idx =
      Math.abs(
        [...new URL(request.url).pathname].reduce(
          (acc, c) => acc + c.charCodeAt(0),
          0
        )
      ) % healthyBackends.length;

    const target = healthyBackends[idx];
    const upstream = new URL(request.url);
    upstream.host = new URL(target).host;
    upstream.protocol = new URL(target).protocol;

    const proxied = new Request(upstream.toString(), request);
    proxied.headers.set("X-Forwarded-Host", new URL(request.url).host);
    return fetch(proxied);
  },

  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(
      (async () => {
        for (const backend of BACKENDS) {
          const kvKey = `health:${backend}`;
          const prevRaw = await env.HEALTH_KV.get(kvKey);
          const prev: HealthRecord | null = prevRaw ? JSON.parse(prevRaw) : null;

          const current = await pingBackend(backend);
          await env.HEALTH_KV.put(kvKey, JSON.stringify(current), {
            expirationTtl: 300, // 5-minute safety expiry
          });

          // Alert on state transition
          if (prev && prev.status !== current.status) {
            await env.ALERT_QUEUE.send({
              backend,
              from: prev.status,
              to: current.status,
              latencyMs: current.latencyMs,
              ts: current.ts,
            });
          }
        }
      })()
    );
  },

  async queue(batch: MessageBatch, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const payload = msg.body as {
        backend: string;
        from: string;
        to: string;
        latencyMs: number;
        ts: number;
      };
      const emoji = payload.to === "healthy" ? ":white_check_mark:" : ":rotating_light:";
      await fetch(env.SLACK_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `${emoji} *Backend health transition*\n*Backend:* ${payload.backend}\n*Status:* ${payload.from} → ${payload.to}\n*Latency:* ${payload.latencyMs}ms`,
        }),
      });
      msg.ack();
    }
  },
};
```

## Section 3 — Integration / Testing

```bash
# Create KV namespace
wrangler kv namespace create HEALTH_KV
# Update wrangler.toml with the returned id, then:

# Create the alerts queue
wrangler queues create health-alerts

# Run locally (health checks will fire against real endpoints)
wrangler dev --local

# Trigger the scheduled handler manually in dev
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"

# Inspect KV state
wrangler kv key list --namespace-id=<id>
wrangler kv key get --namespace-id=<id> "health:https://api-1.internal.example.com"

# Deploy
wrangler deploy

# Tail live logs to watch health cycles
wrangler tail --format=pretty
```

---

## Anti-patterns
- **Pinging backends on every request** — adds per-request latency and hammers backends; use the cron-to-KV pattern instead.
- **Using only HTTP 200 as healthy** — check response body or a `/health` contract; a 200 from an error page is misleading.
- **No stale-record TTL** — if the cron stops firing, stale "healthy" records will route to dead backends; set `expirationTtl` as a safety net.
- **Synchronous Slack calls in the cron handler** — push to a Queue and handle in a consumer to avoid blocking the health-check loop.

---

## Gotchas
- KV has eventual consistency; a backend marked unhealthy may still receive one request from an edge node with a slightly stale read.
- The free KV tier has a 1,000 writes/day limit; with 3 backends and a 1-minute cron that is 4,320 writes/day — upgrade to paid or reduce cron frequency.
- `ctx.waitUntil()` is required in `scheduled()` so async work isn't cut off when the handler returns.
- Queue consumers must `msg.ack()` explicitly or the message will be redelivered.

---

## Verification

```bash
# Confirm cron trigger is registered
wrangler triggers list

# Manually mark a backend unhealthy and verify 503 + Retry-After
wrangler kv key put --namespace-id=<id> \
  'health:https://api-1.internal.example.com' \
  '{"status":"unhealthy","latencyMs":9999,"ts":9999999999999}'

curl -i https://load-balancer.<your-subdomain>.workers.dev/
# Expect: HTTP/1.1 503, Retry-After: 30

# Check queue message count
wrangler queues list
```

---

## Related
- `workers-bot-management-cf-score-kv.md`
- `cloudflare-tunnel-private-service-workers.md`

---

## Sources
- Cloudflare Workers Scheduled Events — https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Workers KV — https://developers.cloudflare.com/kv/
