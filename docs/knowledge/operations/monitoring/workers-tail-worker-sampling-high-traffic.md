# Workers Tail Worker Sampling Strategies for High-Traffic Filtering

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use Case

You have a Cloudflare Worker handling millions of requests per day. Connecting a Tail Worker to capture every log event is either hitting Cloudflare's Tail Worker invocation limits, generating so much telemetry data that downstream storage costs are unsustainable, or overwhelming your observability backend with noise. You need a principled strategy to sample logs and events at the edge—preserving statistical fidelity, ensuring errors and slow requests are never dropped, and keeping high-volume informational traffic at a manageable sample rate.

---

## Context

A **Tail Worker** is a special Cloudflare Worker that receives a batch of `TailEvent` objects representing completed requests from a *producer* Worker. Each `TailEvent` includes the request metadata, response status, CPU time, wall-clock duration, any `console.log()` calls made during the request, and any uncaught exceptions.

Tail Workers are subject to their own compute budget and execution limits. When the volume of tail events exceeds what your pipeline can handle efficiently, you need to implement **head-based sampling** (decide to sample at the start of processing), **tail-based sampling** (decide after inspecting the event), or **reservoir sampling** (maintain a statistically representative sample over time).

Key constraints to keep in mind:

- Tail Worker invocations are batched: one invocation receives up to 100 `TailEvent` objects.
- Tail Workers have the same 10 ms CPU time limit per invocation (in the Bundled usage model) or 30 s wall time in the Unbound model.
- You cannot "buffer" events across invocations to build a global reservoir—each invocation is stateless unless you use Durable Objects or KV.
- Sampling decisions made in a Tail Worker do not affect the producer Worker's execution; they only control what telemetry you forward downstream.

---

## Strategy 1: Deterministic Hash-Based Head Sampling

The simplest approach: hash a stable attribute of each event (e.g., the request ID or `cf-ray` header) and keep events whose hash falls below a threshold. This is reproducible—the same request always makes the same sampling decision—which matters when correlating logs with traces.

```typescript
// tail-worker/src/index.ts

interface Env {
  AXIOM_API_KEY: string;
  SAMPLE_RATE: string; // e.g. "0.1" = 10%
}

async function hashString(input: string): Promise<number> {
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = new Uint8Array(hashBuffer);
  // Use first 4 bytes as a uint32, normalise to [0, 1)
  const uint32 = (hashArray[0] << 24) | (hashArray[1] << 16) | (hashArray[2] << 8) | hashArray[3];
  return (uint32 >>> 0) / 0x100000000;
}

export default {
  async tail(events: TailEvent[], env: Env, ctx: ExecutionContext): Promise<void> {
    const sampleRate = parseFloat(env.SAMPLE_RATE ?? "0.1");

    const sampledEvents: TailEvent[] = [];

    for (const event of events) {
      // Always keep errors and slow requests regardless of sample rate
      const hasError = event.exceptions.length > 0 || event.outcome === "exception";
      const isSlow = event.wallTime > 5000; // > 5 s

      if (hasError || isSlow) {
        sampledEvents.push(event);
        continue;
      }

      // Deterministic sampling on cf-ray for reproducibility
      const rayId = event.request.headers["cf-ray"] ?? event.request.url;
      const hash = await hashString(rayId);

      if (hash < sampleRate) {
        sampledEvents.push(event);
      }
    }

    if (sampledEvents.length === 0) return;

    ctx.waitUntil(forwardToAxiom(sampledEvents, env.AXIOM_API_KEY, sampleRate));
  },
};

async function forwardToAxiom(
  events: TailEvent[],
  apiKey: string,
  sampleRate: number
): Promise<void> {
  const body = events.map((e) => ({
    _time: new Date(e.eventTimestamp).toISOString(),
    ray: e.request.headers["cf-ray"],
    url: e.request.url,
    method: e.request.method,
    status: e.response?.status,
    outcome: e.outcome,
    wallTime: e.wallTime,
    cpuTime: e.cpuTime,
    // Annotate with sample rate so downstream can extrapolate counts
    sampleRate,
    sampledFraction: sampleRate,
    exceptionsCount: e.exceptions.length,
    exceptions: e.exceptions.map((ex) => ({ message: ex.message, name: ex.name })),
  }));

  await fetch("https://api.axiom.co/v1/datasets/workers-logs/ingest", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
}
```

**Annotation is mandatory.** Every sampled event must carry `sampleRate` so that downstream dashboards can multiply counts by `1/sampleRate` to reconstruct true request volume.

---

## Strategy 2: Priority-Lane Sampling with Multiple Rates

Different request categories warrant different sample rates. A health-check endpoint hitting every 10 seconds from an uptime monitor should be sampled at 1%; a payment webhook should be sampled at 100%.

```typescript
// tail-worker/src/sampling.ts

export type SampleRule = {
  name: string;
  match: (event: TailEvent) => boolean;
  rate: number; // 0–1
};

export const SAMPLE_RULES: SampleRule[] = [
  // Critical: always keep
  {
    name: "errors",
    match: (e) => e.exceptions.length > 0 || e.outcome === "exception",
    rate: 1.0,
  },
  {
    name: "slow-requests",
    match: (e) => e.wallTime > 3000,
    rate: 1.0,
  },
  {
    name: "payment-webhooks",
    match: (e) => e.request.url.includes("/webhooks/payment"),
    rate: 1.0,
  },

  // High value: 50% sample
  {
    name: "api-authenticated",
    match: (e) => !!e.request.headers["authorization"],
    rate: 0.5,
  },

  // Health / synthetic: 1% sample
  {
    name: "health-checks",
    match: (e) =>
      e.request.url.endsWith("/health") || e.request.url.endsWith("/ping"),
    rate: 0.01,
  },

  // Static assets: 0.1%
  {
    name: "static-assets",
    match: (e) => /\.(js|css|png|jpg|woff2|ico)(\?|$)/.test(e.request.url),
    rate: 0.001,
  },

  // Default
  {
    name: "default",
    match: () => true,
    rate: 0.1,
  },
];

export function classifyEvent(event: TailEvent): SampleRule {
  for (const rule of SAMPLE_RULES) {
    if (rule.match(event)) return rule;
  }
  // Unreachable if default rule exists, but satisfy TypeScript
  return { name: "default", match: () => true, rate: 0.1 };
}
```

```typescript
// tail-worker/src/index.ts (updated)

import { classifyEvent } from "./sampling";

export default {
  async tail(events: TailEvent[], env: Env, ctx: ExecutionContext): Promise<void> {
    const toForward: Array<{ event: TailEvent; sampleRate: number; lane: string }> = [];

    for (const event of events) {
      const rule = classifyEvent(event);

      // Simple uniform random for per-event decision (not deterministic, but fast)
      if (Math.random() < rule.rate) {
        toForward.push({ event, sampleRate: rule.rate, lane: rule.name });
      }
    }

    if (toForward.length === 0) return;

    ctx.waitUntil(forwardEvents(toForward, env));
  },
};
```

---

## Strategy 3: Adaptive Rate Limiting with KV-Backed Counters

When traffic spikes unexpectedly, fixed rates may still overwhelm your pipeline. Adaptive sampling reads the current throughput from KV and dynamically reduces the sample rate to stay under a target events-per-minute ceiling.

```typescript
// tail-worker/src/adaptive.ts

const TARGET_EPM = 500; // target: 500 forwarded events per minute

export async function computeAdaptiveRate(
  kv: KVNamespace,
  windowKey: string, // e.g. "epm:2026082209" (YYYYMMDDHH)
  batchSize: number
): Promise<number> {
  const raw = await kv.get(windowKey);
  const currentCount = raw ? parseInt(raw, 10) : 0;

  // How many events can we still forward this minute-window?
  const remaining = Math.max(0, TARGET_EPM - currentCount);

  if (remaining === 0) return 0; // shed everything this batch
  if (batchSize === 0) return 1;

  // Rate that would keep us at target
  const rate = Math.min(1, remaining / batchSize);

  // Update counter (fire-and-forget, best-effort)
  const forwarded = Math.floor(batchSize * rate);
  await kv.put(windowKey, String(currentCount + forwarded), { expirationTtl: 120 });

  return rate;
}
```

```typescript
// tail-worker/src/index.ts (adaptive version)

import { computeAdaptiveRate } from "./adaptive";

interface Env {
  KV: KVNamespace;
  AXIOM_API_KEY: string;
}

export default {
  async tail(events: TailEvent[], env: Env, ctx: ExecutionContext): Promise<void> {
    // Always keep errors regardless of adaptive rate
    const errors = events.filter(
      (e) => e.exceptions.length > 0 || e.outcome === "exception"
    );
    const normal = events.filter(
      (e) => e.exceptions.length === 0 && e.outcome !== "exception"
    );

    const minuteKey = `epm:${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "")}`;
    const adaptiveRate = await computeAdaptiveRate(env.KV, minuteKey, normal.length);

    const sampledNormal = normal.filter(() => Math.random() < adaptiveRate);
    const toForward = [...errors, ...sampledNormal];

    if (toForward.length === 0) return;

    ctx.waitUntil(
      forwardBatch(toForward, env.AXIOM_API_KEY, adaptiveRate)
    );
  },
};
```

> **Warning:** KV has eventual consistency. Under extreme burst traffic, multiple Tail Worker invocations racing on the same key can temporarily exceed `TARGET_EPM`. Accept this as a best-effort ceiling, not a hard cap.

---

## Strategy 4: Reservoir Sampling via Durable Objects

For strict statistical guarantees—e.g., you want exactly _k_ representative events per time window—use a Durable Object as a coordinator. Each Tail Worker invocation submits candidates; the DO maintains a reservoir using Vitter's Algorithm R.

```typescript
// durable-objects/src/ReservoirSampler.ts

export class ReservoirSampler implements DurableObject {
  private reservoir: unknown[] = [];
  private seen = 0;
  private readonly k: number;
  private readonly state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
    this.k = 100; // keep 100 events per window
  }

  async fetch(request: Request): Promise<Response> {
    const { action, events } = await request.json<{
      action: "submit" | "drain";
      events?: unknown[];
    }>();

    await this.state.storage.transaction(async (txn) => {
      this.seen = (await txn.get<number>("seen")) ?? 0;
      this.reservoir = (await txn.get<unknown[]>("reservoir")) ?? [];

      if (action === "submit" && events) {
        for (const event of events) {
          this.seen++;
          if (this.reservoir.length < this.k) {
            this.reservoir.push(event);
          } else {
            const j = Math.floor(Math.random() * this.seen);
            if (j < this.k) {
              this.reservoir[j] = event;
            }
          }
        }
        await txn.put("seen", this.seen);
        await txn.put("reservoir", this.reservoir);
      }

      if (action === "drain") {
        const snapshot = [...this.reservoir];
        await txn.put("reservoir", []);
        await txn.put("seen", 0);
        return new Response(JSON.stringify({ events: snapshot, seen: this.seen }), {
          headers: { "Content-Type": "application/json" },
        });
      }
    });

    return new Response("ok");
  }
}
```

```typescript
// tail-worker/src/index.ts (reservoir version)

interface Env {
  SAMPLER: DurableObjectNamespace;
}

export default {
  async tail(events: TailEvent[], env: Env, ctx: ExecutionContext): Promise<void> {
    const id = env.SAMPLER.idFromName("global-reservoir");
    const stub = env.SAMPLER.get(id);

    ctx.waitUntil(
      stub.fetch("https://internal/sampler", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "submit", events }),
      })
    );
  },
};
```

A separate cron Worker calls `action: "drain"` every minute to flush the reservoir to your observability backend.

---

## Strategy 5: wrangler.toml Configuration for Tail Workers

```toml
# wrangler.toml for the producer Worker
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[tail_consumers]]
service = "api-tail-worker"
environment = "production"

# wrangler.toml for the Tail Worker itself
# (separate wrangler.toml in tail-worker/ directory)
name = "api-tail-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "KV"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[vars]
SAMPLE_RATE = "0.1"

[[unsafe.bindings]]
type = "tail_consumer"
name = "TAIL_CONSUMER"
```

---

## Anti-Patterns

**Sampling everything uniformly without special-casing errors.** A 10% sample rate means 90% of your uncaught exceptions are silently dropped. Always route errors to a 100% lane first.

**Using `Math.random()` for deterministic correlation.** If you need to correlate a tail log with a distributed trace, use hash-based sampling on the `cf-ray` or `traceparent` header so the sampling decision is reproducible.

**Storing per-request state in the Tail Worker's global scope.** Tail Workers share the V8 isolate between invocations on the same infrastructure thread, so global mutable state bleeds between batches. Keep all mutable state in KV or Durable Objects.

**Annotating sampled events with `sampleRate = 1.0` when your rate was actually 0.1.** Downstream aggregation tools multiply by `1/sampleRate` to reconstruct counts. Wrong annotation = wrong counts.

**Running CPU-intensive processing (encryption, compression) synchronously inside the tail loop.** You have 10 ms CPU. Do heavy work async in `ctx.waitUntil()`.

---

## Gotchas

- **Tail Workers do not retry on failure.** If your forwarding call to Axiom/Loki/R2 fails, those events are lost. Implement a dead-letter path to KV for critical events.
- **`event.wallTime` includes time waiting for I/O**—it is not pure CPU time. A 5-second `wallTime` might be a slow upstream, not a slow Worker. Use `event.cpuTime` for compute anomalies.
- **The `outcome` field.** Possible values are `"ok"`, `"exception"`, `"exceededCpu"`, `"exceededMemory"`, `"scriptNotFound"`, `"canceled"`. Sample `"exceededCpu"` and `"exceededMemory"` at 100%—they indicate limit violations.
- **Batches are not chronologically ordered.** Events in a single Tail Worker invocation may span several seconds of real time.
- **Tail Workers are not invoked for requests served from cache.** Cache hits at the Cloudflare edge never reach your Worker or its Tail Worker.
- **KV TTL conflicts.** If you use short TTLs (< 60 s) for adaptive counters, be careful—KV's minimum TTL for `expirationTtl` is 60 seconds.

---

## Verification

```bash
# 1. Deploy tail worker and producer
wrangler deploy --config tail-worker/wrangler.toml
wrangler deploy --config wrangler.toml

# 2. Send 1000 test requests
for i in $(seq 1 1000); do
  curl -s "https://api-worker.example.workers.dev/test" > /dev/null
done

# 3. Check Axiom / your backend for event count
# Expect ~100 events with sampleRate=0.1 annotation
# Expect exact count for any error responses

# 4. Verify sampleRate annotation present
# In Axiom query:
# dataset="workers-logs" | count(), avg(sampleRate) by lane

# 5. Validate error always sampled
curl -s "https://api-worker.example.workers.dev/trigger-error" > /dev/null
# Check that error appears in Axiom with sampleRate=1.0 and lane="errors"
```

```typescript
// Unit test for classifyEvent
import { classifyEvent, SAMPLE_RULES } from "./sampling";

const errorEvent = {
  exceptions: [{ message: "oops", name: "Error" }],
  outcome: "exception",
  request: { url: "https://example.com/api", method: "GET", headers: {} },
  wallTime: 100,
} as unknown as TailEvent;

const rule = classifyEvent(errorEvent);
console.assert(rule.name === "errors", "Errors must hit the 100% lane");
console.assert(rule.rate === 1.0, "Error sample rate must be 1.0");
```

---

## Related

- `workers-tail-real-time-log-streaming.md` — foundational Tail Worker setup and streaming to Loki
- `workers-tail-worker-pii-minimization-and-otel-decision.md` — PII scrubbing before forwarding
- `tail-sampling-strategies.md` — OpenTelemetry collector tail sampling (different layer)
- `distributed-tracing-workers-d1-durable-objects-otel.md` — trace context propagation
- `log-sampling-strategies.md` — general log sampling theory
- `workers-logpush-observability-pipeline.md` — Logpush as an alternative to Tail Workers

---

## Sources

- [Cloudflare Tail Workers documentation](https://developers.cloudflare.com/workers/observability/tail-workers/)
- [Workers runtime limits](https://developers.cloudflare.com/workers/platform/limits/)
- Vitter, J.S. (1985). "Random sampling with a reservoir." *ACM Transactions on Mathematical Software*, 11(1), 37–57.
- [Cloudflare Durable Objects](https://developers.cloudflare.com/durable-objects/)
- [OpenTelemetry sampling specification](https://opentelemetry.io/docs/concepts/sampling/)
