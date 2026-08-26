# Chaos Engineering and Fault Injection on Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your distributed system on Cloudflare Workers passes all unit and integration tests, but you have
no confidence it degrades gracefully when a downstream D1 database is slow, a KV namespace returns
stale data, or a Durable Object hibernates mid-request. You need a structured way to inject
controlled failures so you discover weaknesses before production does.

## Context

Chaos engineering is the discipline of deliberately introducing failure into a running system to
build confidence in its resilience. On the Cloudflare stack the relevant failure modes are:

- D1 query latency spikes or returning errors
- KV cache misses / cold reads with replication lag
- Downstream service binding timeouts
- Durable Object eviction under memory pressure
- Queue consumer failures causing dead-letter accumulation
- R2 PUT operations racing with GET under eventual consistency

Because Workers run in a sandboxed V8 isolate you cannot hook OS-level syscalls. Fault injection
must be implemented at the application boundary using interceptor wrappers controlled by a chaos
flag stored in KV or a Durable Object.

## Chaos Controller Durable Object

The chaos controller is a single Durable Object that holds the current chaos experiment state.
Any Worker can query it to determine whether to inject a fault on a given service.

```typescript
// chaos-controller.ts
export interface ChaosRule {
  target: string;           // e.g. "d1", "kv", "service:payment"
  fault: "latency" | "error" | "partial";
  probability: number;      // 0.0 – 1.0
  latencyMs?: number;
  errorCode?: number;
  expiresAt: number;        // epoch ms
}

export class ChaosController extends DurableDo {
  private rules: ChaosRule[] = [];

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "PUT" && url.pathname === "/rules") {
      this.rules = await request.json<ChaosRule[]>();
      await this.storage.put("rules", this.rules);
      return new Response("ok");
    }
    if (url.pathname === "/rules") {
      const stored = await this.storage.get<ChaosRule[]>("rules");
      return Response.json(stored ?? []);
    }
    const target = url.searchParams.get("target") ?? "";
    const now = Date.now();
    const active = (this.rules).filter(
      r => r.target === target && r.expiresAt > now
    );
    return Response.json(active);
  }

  async initialize() {
    this.rules = (await this.storage.get<ChaosRule[]>("rules")) ?? [];
  }
}
```

## Fault-Injecting D1 Wrapper

Wrap the real D1 binding so the rest of the application never references D1 directly.

```typescript
// chaos-d1.ts
import type { ChaosRule } from "./chaos-controller";

async function activeFault(
  env: Env,
  target: string
): Promise<ChaosRule | null> {
  if (!env.CHAOS_ENABLED) return null;
  const id = env.CHAOS_CONTROLLER.idFromName("global");
  const stub = env.CHAOS_CONTROLLER.get(id);
  const res = await stub.fetch(
    `https://chaos/rules?target=${target}`
  );
  const rules = await res.json<ChaosRule[]>();
  for (const rule of rules) {
    if (Math.random() < rule.probability) return rule;
  }
  return null;
}

async function maybeDelay(rule: ChaosRule | null) {
  if (rule?.fault === "latency" && rule.latencyMs) {
    await new Promise(r => setTimeout(r, rule.latencyMs));
  }
}

export function chaosD1(real: D1Database, env: Env): D1Database {
  return new Proxy(real, {
    get(target, prop) {
      if (prop !== "prepare" && prop !== "batch" && prop !== "exec") {
        return (target as any)[prop];
      }
      return (...args: unknown[]) => {
        return {
          async first<T = Record<string, unknown>>() {
            const fault = await activeFault(env, "d1");
            if (fault?.fault === "error") {
              throw new Error(`[chaos] D1 simulated error ${fault.errorCode}`);
            }
            await maybeDelay(fault);
            const stmt = (target.prepare as Function)(...args);
            return stmt.first<T>();
          },
          async all<T = Record<string, unknown>>() {
            const fault = await activeFault(env, "d1");
            if (fault?.fault === "error") {
              throw new Error(`[chaos] D1 simulated error ${fault.errorCode}`);
            }
            await maybeDelay(fault);
            const stmt = (target.prepare as Function)(...args);
            return stmt.all<T>();
          },
          async run() {
            const fault = await activeFault(env, "d1");
            if (fault?.fault === "error") {
              throw new Error(`[chaos] D1 simulated error`);
            }
            await maybeDelay(fault);
            const stmt = (target.prepare as Function)(...args);
            return stmt.run();
          },
        };
      };
    },
  });
}
```

## Experiment Runner in a Cron Worker

Define experiments as data and activate them via the controller. A Cron Trigger can run
time-boxed experiments automatically.

```typescript
// experiment-scheduler.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const experiment: ChaosRule[] = [
      {
        target: "d1",
        fault: "latency",
        probability: 0.3,
        latencyMs: 800,
        expiresAt: Date.now() + 5 * 60 * 1000, // 5 minutes
      },
    ];
    const id = env.CHAOS_CONTROLLER.idFromName("global");
    const stub = env.CHAOS_CONTROLLER.get(id);
    await stub.fetch(new Request("https://chaos/rules", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(experiment),
    }));
    // Log the start of the experiment
    env.ANALYTICS.writeDataPoint({
      blobs: ["chaos_experiment_started", "d1_latency"],
      doubles: [0.3, 800],
      indexes: ["experiment"],
    });
  },
};
```

## Observing Blast Radius with Analytics Engine

Capture error rates and p99 latency during and after the experiment to measure blast radius.

```typescript
// worker-instrumented.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const start = Date.now();
    let status = 200;
    try {
      const db = chaosD1(env.DB, env);
      const result = await db.prepare("SELECT * FROM items LIMIT 10").all();
      return Response.json(result.results);
    } catch (err) {
      status = 500;
      return new Response("Service error", { status: 500 });
    } finally {
      env.ANALYTICS.writeDataPoint({
        blobs: ["request_complete", String(status)],
        doubles: [Date.now() - start],
        indexes: ["requests"],
      });
    }
  },
};
```

## Steady-State Hypothesis Verification

Before and after an experiment, verify the system's normal behaviour baseline.

```typescript
// hypothesis.ts
export async function verifySteadyState(env: Env): Promise<boolean> {
  const start = Date.now();
  try {
    const result = await env.DB.prepare(
      "SELECT count(*) as c FROM items"
    ).first<{ c: number }>();
    const latency = Date.now() - start;
    // Hypothesis: health check responds in < 200 ms with valid data
    return latency < 200 && (result?.c ?? 0) > 0;
  } catch {
    return false;
  }
}
```

## Anti-patterns

- Running chaos experiments in production without stakeholder awareness and a kill switch.
- Injecting faults on every request (probability 1.0) in a shared environment — use 0.01–0.10.
- Forgetting to set `expiresAt` — a stale rule silently degrades production indefinitely.
- Coupling chaos logic to business logic. Always inject at the boundary wrapper, never inline.
- Logging `CHAOS_ENABLED` in public response headers — leaks internal state to clients.

## Gotchas

- The Chaos Controller DO must be accessed over the service binding namespace, not a public URL,
  so only Workers in the same account can activate experiments.
- `setTimeout` inside a Worker is valid only during an active I/O context. Inject latency with
  `await scheduler.wait(ms)` if available, otherwise a `Promise`-wrapped `setTimeout`.
- The DO `initialize()` lifecycle hook is called on every cold start — load rules from storage
  there to avoid an extra fetch on the first experiment query.
- KV chaos rules require a special case: wrapping `env.KV` similarly to the D1 wrapper above.

## Verification

1. Deploy the `ChaosController` DO and `experiment-scheduler` cron to staging.
2. Activate the latency experiment and confirm p99 latency rises in Analytics Engine.
3. Confirm your circuit breaker (see `circuit-breaker-kv-state-machine.md`) trips at the
   configured threshold.
4. Let `expiresAt` lapse and verify latency returns to baseline without a deployment.
5. Run the steady-state hypothesis before and after — both calls must return `true`.

## Related

- `circuit-breaker-kv-state-machine.md`
- `retry-storm-prevention-workers-jitter-backoff.md`
- `bulkhead-isolation-workers-service-bindings.md`
- `observability-architecture.md`
- `workers-tail-handlers-observability.md`

## Sources

- Netflix Chaos Engineering principles: https://principlesofchaos.org/
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
