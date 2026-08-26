# Workers Tail Event Loss During Deploy Rollover Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom

After a Workers deploy, the observability pipeline (Logpush → R2 → analytics) showed a 4–6 minute gap in tail events for every deployment. During high-traffic incidents this was the worst possible time to lose logs — the deploy that introduced a bug was the exact window where events went silent. The gap was consistent across all deployments and reproducible in staging.

## Context

The application uses a Tail Worker to capture structured logs from the primary Worker and forward them to an R2-backed Logpush sink. The primary Worker is deployed roughly 8 times per day via `wrangler deploy`. During each deploy, Cloudflare performs a rolling update: new Worker script version activates gradually, while the old version drains its in-flight requests. The Tail Worker is bound to a specific script version. Events emitted by the old script version after the new script is active are dropped by the Tail Worker binding if the Tail Worker itself has not yet been re-bound to the old version's final drain window.

---

## Root Cause: Tail Worker Binding Is Version-Scoped; Draining Old Version Emits to No Consumer

When `wrangler deploy` is called:
1. New script version becomes the active version for new requests.
2. Old script version continues to serve in-flight requests for up to 30 s (the drain window).
3. The Tail Worker binding is updated to point to the new script version.
4. Events from the draining old version have no Tail Worker consumer — they are discarded.

Additionally, Tail Workers themselves go through a cold start on deploy, causing a second gap of 2–10 s at the start of the new binding.

```typescript
// wrangler.toml — BEFORE: single tail worker, loses events during rollover
[[tail_consumers]]
service = "log-forwarder"

// The log-forwarder Worker is redeployed at the same time as the primary.
// During the overlap window: old primary → no tail consumer.
// New primary → cold-starting tail consumer (first events may drop).
```

## Fix Step 1: Deploy the Tail Worker Before the Primary Worker

Separate the deploy pipeline so the Tail Worker is always ahead of the primary:

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy-tail:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npx wrangler deploy --name log-forwarder

  deploy-primary:
    needs: deploy-tail
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npx wrangler deploy --name api-worker
```

This ensures the Tail Worker is warmed and bound before the primary Worker rolls over. The drain window of the old primary still has an active Tail Worker to receive its events.

## Fix Step 2: Buffer Tail Events in a Durable Object for the Drain Window

For critical event types (errors, payments), add a Durable Object buffer so events are not lost even during the brief cold-start gap:

```typescript
// src/tail/event-buffer.ts
export class TailEventBuffer implements DurableObject {
  private events: TailEvent[] = [];

  async fetch(request: Request): Promise<Response> {
    if (request.method === "POST") {
      const event = await request.json<TailEvent>();
      this.events.push(event);

      // Flush immediately to Logpush sink
      await this.flush();
      return new Response("ok");
    }
    return new Response("method not allowed", { status: 405 });
  }

  private async flush(): Promise<void> {
    if (this.events.length === 0) return;
    const batch = this.events.splice(0);
    // Forward to R2 Logpush endpoint
    await fetch(this.env.LOGPUSH_ENDPOINT, {
      method: "POST",
      body: JSON.stringify(batch),
      headers: { "Content-Type": "application/json" },
    });
  }
}
```

## Fix Step 3: Add a Sequence Number to Tail Events for Gap Detection

Without sequence numbers, a log gap is invisible until you diff two time ranges manually. Add a monotonic counter:

```typescript
// src/tail/forwarder.ts
let sequenceCounter = 0;

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    const enriched = events.map((event) => ({
      ...event,
      meta: {
        seqNo: ++sequenceCounter,
        tailWorkerVersion: env.WORKER_VERSION ?? "unknown",
        forwardedAt: Date.now(),
      },
    }));

    await env.BUCKET.put(
      `logs/${Date.now()}-${enriched[0].meta.seqNo}.ndjson`,
      enriched.map((e) => JSON.stringify(e)).join("\n"),
    );
  },
};
```

An analytics query that finds sequence gaps signals a tail event loss window.

## Fix Step 4: Emit a Heartbeat Event Every 30 Seconds

Tail Workers only fire when the primary Worker handles a request. Under low traffic, gaps look like event loss. Emit a synthetic heartbeat from a cron trigger to keep the pipeline warm and provide a baseline for gap detection:

```typescript
// src/index.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(
      fetch("https://internal.example.com/heartbeat", {
        method: "POST",
        body: JSON.stringify({ type: "heartbeat", ts: Date.now() }),
      }),
    );
  },
};
```

```toml
# wrangler.toml
[[triggers]]
crons = ["* * * * *"]  # every minute
```

## Fix Step 5: Alert on Tail Event Gaps Using Analytics Engine

```typescript
// scripts/check-tail-gap.ts  (run from a monitoring Worker on cron)
export async function detectTailGap(env: Env): Promise<void> {
  const result = await env.DB.prepare(
    `SELECT
       MAX(seqNo) - MIN(seqNo) - COUNT(*) + 1 AS gap_count,
       MIN(forwardedAt) AS window_start,
       MAX(forwardedAt) AS window_end
     FROM tail_events
     WHERE forwardedAt > unixepoch() * 1000 - 600000`, // last 10 min
  ).first<{ gap_count: number; window_start: number; window_end: number }>();

  if (result && result.gap_count > 0) {
    console.error(
      JSON.stringify({
        level: "error",
        event: "tail_event_gap_detected",
        gapCount: result.gap_count,
        windowStart: result.window_start,
        windowEnd: result.window_end,
      }),
    );
    // Page on-call via PagerDuty / Better Stack
    await fetch(env.ALERT_WEBHOOK, {
      method: "POST",
      body: JSON.stringify({ text: `Tail event gap: ${result.gap_count} events missing` }),
    });
  }
}
```

## Fix Step 6: Validate the Fix by Simulating a Deploy Under Load

```bash
# Run in staging: hammer the Worker with requests while deploying
wrk -t4 -c100 -d120s https://staging.example.com/api/probe &
sleep 30
wrangler deploy --name api-worker  # deploy mid-load
sleep 90
kill %1

# Then check: are there any gap events in the tail log for the deploy window?
wrangler d1 execute LOGS_DB --command \
  "SELECT COUNT(*) FROM tail_events WHERE type = 'gap_marker'"
```

Expected result after fix: 0 gap markers.

---

## Anti-Patterns

- **Deploying the Tail Worker and primary Worker in the same pipeline step.** If both deploy simultaneously, the old primary drains without a consumer.
- **Not sequencing tail events.** Without sequence numbers, a 4-minute gap looks identical to a quiet period. You only discover the loss when investigating an incident.
- **Assuming Tail Workers are zero-latency and zero-cold-start.** The first invocation of a Tail Worker after a deploy incurs a cold start. Critical events during that window may be lost.
- **Using tail events as the sole source of truth for payment or error events.** Tail Workers are best-effort; complement them with structured logging via `ctx.waitUntil` + R2/D1 writes inside the primary Worker.

## Gotchas

- Tail Workers are limited to 1000 events per invocation and 2000 invocations per second per account. Under extremely high traffic, Cloudflare samples tail events before delivery — this is separate from the deploy-rollover loss.
- The `WORKER_VERSION` binding is not available by default; you must set it as an environment variable via wrangler.toml or a CI variable.
- Durable Object writes inside a Tail Worker count against the Tail Worker's own CPU budget (30 ms on free, 30 s on paid). Keep the buffer logic minimal.
- Tail Workers bound via `tail_consumers` in wrangler.toml apply to the production environment. Staging may need its own separate Tail Worker declaration to avoid cross-contamination of log streams.

## Verification

1. Zero tail event gaps detected in staging deploy simulation (step 6 above returns 0).
2. Sequence gap alerts fire zero times during normal deploys in production for 2 weeks post-fix.
3. Heartbeat events appear every 60 s in the log sink, confirming the pipeline is alive.
4. The 4–6 minute observability blackout after deploys is eliminated — log events appear continuously through the deploy rollover window.
5. CI enforces `deploy-tail` completes before `deploy-primary` on every merge to main.

## Related

- `workers-tail-worker-sampling-observability-gap.md`
- `logpush-r2-backpressure-dropped-observability.md`
- `monitor-before-and-after-deploy.md`
- `zero-downtime-deployment-workers.md`
- `telemetry-sampling-must-retain-rare-failures.md`

## Sources

- Cloudflare Workers Tail Workers: https://developers.cloudflare.com/workers/observability/logs/tail-workers/
- Workers Deploy and Versioning: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Workers Limits — Tail Workers: https://developers.cloudflare.com/workers/platform/limits/#tail-workers
- Cloudflare Logpush: https://developers.cloudflare.com/logs/about/
