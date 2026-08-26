# Workers AI Model Warm-Up via Cron Triggers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Anonymous social platform (example project) serves user-generated content through multiple
Workers AI models: a sentiment classifier, an embedding model, and a toxicity scorer.
First requests after a model is idle arrive with 800–2 000 ms of additional latency
("cold model" behaviour on Cloudflare's GPU fleet). Spiky traffic patterns — e.g. after
a viral post or a scheduled push notification — cause the first wave of users to hit
stale-cold models simultaneously, producing visible latency spikes and occasional
`execution model timeout` errors.

Goal: keep models perpetually warm during active hours so the P99 response time stays
below 400 ms, while burning zero unnecessary GPU tokens when the platform is idle.

---

## Context

Workers AI runs inference on Cloudflare's globally distributed GPU fleet. A model that
has not been used recently may be evicted from active memory on a given colocate, and
the next request incurs a reload penalty. This is distinct from a Worker cold-start:
the Worker JS runtime starts in <5 ms; the model load is the slow step.

Cloudflare Cron Triggers fire a Worker on a schedule with sub-minute granularity
(minimum 1-minute intervals). A cron trigger can call `env.AI.run()` with a minimal
dummy payload just to exercise the model load path, then discard the result. This
occupies negligible GPU time (~10–30 tokens) but keeps the model resident in GPU
memory on nearby colocation points.

The warm-up Worker must:
- Run on a schedule that matches platform activity windows
- Not pollute analytics or D1 logs with fake inference events
- Be observable so on-call engineers can confirm it is firing

---

## Schedule Design: Match Traffic Windows

Use different cron expressions for peak vs. off-peak hours. Cloudflare Cron Triggers
support multiple schedules on one Worker.

```toml
# wrangler.toml
name = "example project-model-warmup"
main = "src/warmup.ts"
compatibility_date = "2026-01-01"

[ai]
binding = "AI"

[[triggers.crons]]
crons = [
  "*/2 6-23 * * *",   # every 2 min during active hours (06:00–23:59 UTC)
  "*/10 0-5 * * *",   # every 10 min during night hours (00:00–05:59 UTC)
]
```

---

## Warm-Up Worker Implementation

```typescript
// src/warmup.ts
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  ANALYTICS: AnalyticsEngineDataset;
}

// Minimal payloads — chosen to be as short as possible while
// still exercising the full model load + inference path.
const WARMUP_TASKS: Array<{
  model: string;
  input: Parameters<Ai["run"]>[1];
}> = [
  {
    model: "@cf/baai/bge-base-en-v1.5",
    input: { text: "warmup" },
  },
  {
    model: "@cf/huggingface/distilbert-sst-2-int8",
    input: { text: "warmup" },
  },
  {
    model: "@cf/meta/llama-3.1-8b-instruct",
    input: {
      messages: [{ role: "user", content: "hi" }],
      max_tokens: 1,
    },
  },
];

export default {
  async scheduled(
    _event: ScheduledEvent,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    const start = Date.now();

    // Fire all warm-up inferences in parallel; ignore results.
    const results = await Promise.allSettled(
      WARMUP_TASKS.map(({ model, input }) =>
        // @ts-expect-error – model string is dynamic
        env.AI.run(model, input)
      )
    );

    const failures = results.filter((r) => r.status === "rejected");

    // Emit a single lightweight analytics event; NOT written to D1
    // so it never contaminates usage metrics.
    env.ANALYTICS.writeDataPoint({
      blobs: ["model-warmup"],
      doubles: [Date.now() - start, failures.length],
      indexes: ["warmup"],
    });

    if (failures.length > 0) {
      console.error(
        `[warmup] ${failures.length}/${WARMUP_TASKS.length} models failed to warm`,
        failures
      );
    }
  },
};
```

---

## Guard: Skip Warm-Up When Traffic Is Already Warm

Avoid wasting GPU tokens when real requests are already keeping models hot. Check a KV
counter written by the main application Worker.

```typescript
// wrangler.toml addition
[[kv_namespaces]]
binding = "WARMUP_STATE"
id = "<your-kv-id>"
```

```typescript
// src/warmup.ts — enhanced scheduled handler
export interface Env {
  AI: Ai;
  ANALYTICS: AnalyticsEngineDataset;
  WARMUP_STATE: KVNamespace;
}

export default {
  async scheduled(
    _event: ScheduledEvent,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    // Main app writes "last_real_request_at" (unix epoch ms) on every inference call.
    const lastRealRaw = await env.WARMUP_STATE.get("last_real_request_at");
    const lastReal = lastRealRaw ? parseInt(lastRealRaw, 10) : 0;
    const idleMs = Date.now() - lastReal;

    // If a real request happened within the last 90 s, models are already warm.
    if (idleMs < 90_000) {
      console.log(`[warmup] skipped — last real request ${idleMs}ms ago`);
      return;
    }

    // …proceed with warm-up tasks as above
  },
};
```

---

## Application Worker: Record Last Real Request

```typescript
// src/inference-worker.ts  (excerpt)
export async function runInferenceWithWarmupTracking(
  env: Env,
  model: string,
  input: unknown
) {
  // Fire-and-forget; never await to avoid adding latency on the hot path.
  env.WARMUP_STATE.put(
    "last_real_request_at",
    String(Date.now()),
    { expirationTtl: 3600 }
  );

  return env.AI.run(model as Parameters<Ai["run"]>[0], input as never);
}
```

---

## Observability: Verify Warm-Up Is Working

Query Analytics Engine to confirm the cron is firing and models are succeeding:

```sql
-- Cloudflare Analytics Engine SQL API
SELECT
  toStartOfMinute(timestamp) AS minute,
  SUM(double2) AS warmup_failures,
  COUNT() AS warmup_runs
FROM analytics_events
WHERE blob1 = 'model-warmup'
  AND timestamp > now() - INTERVAL '1' HOUR
GROUP BY minute
ORDER BY minute DESC
```

Compare real-request P99 latency before/after enabling the warm-up Worker using
Workers Analytics or a tail worker that writes latency percentiles to D1:

```typescript
// src/tail-worker.ts
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      if (event.scriptName === "example project-inference") {
        const wallMs = event.wallTime;
        await env.DB.prepare(
          "INSERT INTO inference_latency (ts, wall_ms) VALUES (?, ?)"
        )
          .bind(Date.now(), wallMs)
          .run();
      }
    }
  },
};
```

---

## Anti-patterns

- **Warming every model every minute regardless of time zone traffic** — burns GPU
  budget unnecessarily at 3 AM UTC if your user base is EU/US only.
- **Using real user content in warm-up payloads** — the warm-up result is discarded;
  using real content risks a privacy log trail in AI Gateway for data that produces no
  value.
- **Writing warm-up events to D1 usage tables** — inflates per-user cost accounting.
  Use Analytics Engine with a distinct `blob1` discriminator instead.
- **Awaiting warm-up inside the critical request path** — warm-up must live in the
  scheduled handler, never blocking a live request.

---

## Gotchas

- Cron Triggers fire from Cloudflare's scheduler infrastructure, not from a PoP near
  your users. The warm-up reaches the GPU nodes closest to the scheduler's PoP, which
  may differ from the PoP your users hit. This is acceptable: Cloudflare's GPU fleet
  is small enough that a warm on one node benefits most nearby requests.
- `AI.run()` with `max_tokens: 1` on a chat model still runs the full prefill forward
  pass; the warm-up cost is dominated by model load, not token generation.
- Cron Triggers have a 30-second CPU time limit; `Promise.allSettled` on three models
  easily finishes in <5 s under normal conditions.
- A model version change by Cloudflare resets the warm state regardless of cron
  cadence — expect one cold spike after a provider-side model update.

---

## Verification

1. Deploy the warm-up Worker: `wrangler deploy --config wrangler-warmup.toml`
2. Tail logs: `wrangler tail example project-model-warmup --format=pretty`
3. Confirm scheduled events appear every 2 minutes during peak hours.
4. Run a load test against the main inference Worker immediately after a forced cold
   period (disable cron, wait 5 min, re-enable, run load test) and compare P99 vs.
   baseline.
5. Validate Analytics Engine shows `warmup_failures = 0` across a 24-hour window.

---

## Related

- `ai-cold-start-patterns.md`
- `workers-ai-queue-batch-processing.md`
- `workers-ai-model-benchmarking-latency-profiling.md`
- `ai-gateway-latency-slo-analytics-engine.md`
- `workers-ai-durable-objects-stateful-sessions.md`

---

## Sources

- Cloudflare Cron Triggers docs: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Workers AI models: https://developers.cloudflare.com/workers-ai/models/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Workers Tail Workers: https://developers.cloudflare.com/workers/observability/tail-workers/
