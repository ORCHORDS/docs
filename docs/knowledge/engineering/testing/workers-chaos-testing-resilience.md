# Chaos / Resilience Testing for Cloudflare Workers by Injecting Faults

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Workers service looks healthy until an upstream D1 replica is slow, a KV namespace hits a transient write error, or an external API times out. Without deliberate fault injection, these scenarios are never exercised — the Worker's retry logic, circuit breaker, and fallback paths stay untested until a real incident.

## Context

Cloudflare Workers run at the edge; dependencies (KV, D1, R2, external origins) can fail independently. Chaos testing simulates those failures deterministically inside Vitest + Miniflare by wrapping bindings in proxy objects that inject latency, errors, or timeouts according to a configurable schedule. A cron-triggered Worker can also run chaos rounds against a staging environment.

---

## Solution

### 1. Fault injection middleware for fetch

```typescript
// src/chaos/faultMiddleware.ts
export interface FaultConfig {
  latencyMs?: number;          // artificial delay before forwarding
  errorRate?: number;          // 0–1 probability of returning a 503
  timeoutMs?: number;          // abort the request after N ms
}

/**
 * Wraps a fetch-compatible function with configurable fault injection.
 * Use in tests by replacing `env.UPSTREAM` or calling directly.
 */
export function withFaults(
  inner: typeof fetch,
  config: FaultConfig,
): typeof fetch {
  return async (input, init) => {
    if (config.latencyMs) {
      await new Promise((r) => setTimeout(r, config.latencyMs));
    }
    if (config.errorRate && Math.random() < config.errorRate) {
      return new Response(JSON.stringify({ error: 'chaos_error' }), {
        status: 503,
        headers: { 'content-type': 'application/json' },
      });
    }
    if (config.timeoutMs) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), config.timeoutMs);
      try {
        return await inner(input, { ...init, signal: controller.signal });
      } finally {
        clearTimeout(timer);
      }
    }
    return inner(input, init);
  };
}
```

### 2. KV failure simulation

```typescript
// test/chaos/kvProxy.ts
import type { KVNamespace } from '@cloudflare/workers-types';

export interface KVFaultConfig {
  getErrorRate?: number;     // probability of get() throwing
  putErrorRate?: number;     // probability of put() throwing
  listErrorRate?: number;    // probability of list() throwing
  latencyMs?: number;        // delay added to every operation
}

/** Returns a KVNamespace proxy that injects faults per config. */
export function faultyKV(real: KVNamespace, cfg: KVFaultConfig): KVNamespace {
  const maybeDelay = () =>
    cfg.latencyMs ? new Promise<void>((r) => setTimeout(r, cfg.latencyMs)) : Promise.resolve();

  const maybeFail = (rate = 0) => {
    if (rate > 0 && Math.random() < rate) {
      throw new Error('KV_SIMULATED_FAILURE');
    }
  };

  return new Proxy(real, {
    get(target, prop) {
      if (prop === 'get') {
        return async (...args: Parameters<KVNamespace['get']>) => {
          await maybeDelay();
          maybeFail(cfg.getErrorRate);
          return (target.get as Function)(...args);
        };
      }
      if (prop === 'put') {
        return async (...args: Parameters<KVNamespace['put']>) => {
          await maybeDelay();
          maybeFail(cfg.putErrorRate);
          return (target.put as Function)(...args);
        };
      }
      if (prop === 'list') {
        return async (...args: Parameters<KVNamespace['list']>) => {
          await maybeDelay();
          maybeFail(cfg.listErrorRate);
          return (target.list as Function)(...args);
        };
      }
      return Reflect.get(target, prop);
    },
  }) as unknown as KVNamespace;
}
```

### 3. D1 connection error simulation

```typescript
// test/chaos/d1Proxy.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface D1FaultConfig {
  queryErrorRate?: number;
  latencyMs?: number;
}

/** Returns a D1Database proxy that simulates transient query failures. */
export function faultyD1(real: D1Database, cfg: D1FaultConfig): D1Database {
  const maybeFail = () => {
    if ((cfg.queryErrorRate ?? 0) > 0 && Math.random() < cfg.queryErrorRate!) {
      throw new Error('D1_ERROR: SQLITE_BUSY: database is locked');
    }
  };
  const delay = () =>
    cfg.latencyMs ? new Promise<void>((r) => setTimeout(r, cfg.latencyMs)) : Promise.resolve();

  return new Proxy(real, {
    get(target, prop) {
      if (prop === 'prepare') {
        return (query: string) => {
          const stmt = target.prepare(query);
          return new Proxy(stmt, {
            get(s, method) {
              if (['run', 'all', 'first', 'raw'].includes(String(method))) {
                return async (...args: unknown[]) => {
                  await delay();
                  maybeFail();
                  return (s as any)method;
                };
              }
              return Reflect.get(s, method);
            },
          });
        };
      }
      return Reflect.get(target, prop);
    },
  }) as D1Database;
}
```

### 4. Testing circuit breaker activation

```typescript
// src/circuitBreaker.ts
export class CircuitBreaker {
  private failures = 0;
  private openUntil = 0;

  constructor(
    private readonly threshold: number,
    private readonly cooldownMs: number,
  ) {}

  isOpen(): boolean {
    if (Date.now() < this.openUntil) return true;
    return false;
  }

  recordFailure() {
    this.failures++;
    if (this.failures >= this.threshold) {
      this.openUntil = Date.now() + this.cooldownMs;
      this.failures = 0;
    }
  }

  recordSuccess() {
    this.failures = 0;
  }
}
```

```typescript
// test/chaos/circuitBreaker.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { env } from 'cloudflare:test';
import { faultyKV } from './kvProxy';
import { CircuitBreaker } from '../../src/circuitBreaker';

describe('circuit breaker', () => {
  let cb: CircuitBreaker;

  beforeEach(() => {
    cb = new CircuitBreaker(3, 5_000); // open after 3 failures, cool down 5s
  });

  it('opens after threshold failures from faulty KV', async () => {
    const kv = faultyKV(env.MY_KV, { getErrorRate: 1.0 }); // always fails

    let errorCount = 0;
    for (let i = 0; i < 5; i++) {
      if (cb.isOpen()) break;
      try {
        await kv.get('key');
        cb.recordSuccess();
      } catch {
        cb.recordFailure();
        errorCount++;
      }
    }

    expect(cb.isOpen()).toBe(true);
    expect(errorCount).toBe(3); // exactly threshold
  });

  it('rejects requests while open without hitting KV', async () => {
    // Force open
    for (let i = 0; i < 3; i++) cb.recordFailure();
    expect(cb.isOpen()).toBe(true);

    // Subsequent calls should short-circuit
    let kvHit = false;
    const kv = faultyKV(env.MY_KV, {
      getErrorRate: 0,
      latencyMs: 0,
    });

    if (!cb.isOpen()) {
      await kv.get('key');
      kvHit = true;
    }
    expect(kvHit).toBe(false);
  });
});
```

### 5. Chaos schedule with a cron-triggered Worker

```typescript
// src/chaosWorker.ts  — deploy to staging only
import { faultyKV } from '../test/chaos/kvProxy';

export interface Env {
  MY_KV: KVNamespace;
  CHAOS_RESULTS: KVNamespace;
  ENVIRONMENT: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    if (env.ENVIRONMENT !== 'staging') return; // safety guard

    const scenarios: Array<{ name: string; config: Parameters<typeof faultyKV>[1] }> = [
      { name: 'kv-latency-100ms',  config: { latencyMs: 100 } },
      { name: 'kv-get-50pct-fail', config: { getErrorRate: 0.5 } },
      { name: 'kv-put-100pct-fail',config: { putErrorRate: 1.0 } },
    ];

    const results: Record<string, string> = {};

    for (const { name, config } of scenarios) {
      const faulty = faultyKV(env.MY_KV, config);
      try {
        const start = Date.now();
        await faulty.get('probe-key');
        results[name] = `ok:${Date.now() - start}ms`;
      } catch (e) {
        results[name] = `error:${(e as Error).message}`;
      }
    }

    await env.CHAOS_RESULTS.put(
      `run:${new Date().toISOString()}`,
      JSON.stringify(results),
      { expirationTtl: 86_400 },
    );
  },
};
```

```toml
# wrangler.toml (staging)
[env.staging]
name = "my-worker-staging"

[[env.staging.triggers]]
crons = ["*/15 * * * *"]  # every 15 minutes
```

---

## Implementation Details

- Fault proxies are thin wrappers; they add no production code paths — import them only in test files or staging Workers.
- `errorRate` uses `Math.random()` for deterministic-enough sampling at scale; seed it with `vi.spyOn(Math, 'random')` for precise control in unit tests.
- The cron chaos Worker writes results to a separate KV namespace so the probe does not corrupt live data.
- Circuit breaker thresholds should match production config; test them at exactly `threshold - 1` (stays closed) and `threshold` (opens).

---

## Anti-patterns

- **Running chaos schedules in production** — always gate on `ENVIRONMENT !== 'production'`.
- **Using `setTimeout` delays > 25 s in Workers** — the CPU time limit will kill the isolate first; keep fault latency well under the Worker's subrequest timeout.
- **Testing only the happy path after injecting faults** — verify that fallback responses are correct, not just that the Worker did not crash.
- **Shared global state in fault configs** — use factory functions so each test gets an independent proxy.

---

## Gotchas

- Miniflare's KV does not enforce the real-world rate limits; latency injection is the best approximation of overload.
- `Math.random()` inside Miniflare is deterministic per-isolate run only if the seed is fixed via `--seed` in `workerd`; use `vi.spyOn` for exact control.
- Cron triggers in wrangler need `[triggers]` under the environment stanza, not at the root level, for environment-specific schedules.

---

## Verification

```bash
# Run chaos tests in isolation
npx vitest run test/chaos/

# Trigger the staging cron manually
npx wrangler --env staging dispatch-namespace trigger chaos-worker

# Check chaos run results in KV
npx wrangler --env staging kv key list --namespace-id=<CHAOS_RESULTS_ID>
```

---

## Related

- `documentation/docs/policies/testing/vitest-workers-miniflare.md`
- `documentation/docs/policies/testing/workers-contract-testing-pact.md`
- `documentation/docs/policies/testing/workers-load-testing-k6-cloudflare.md`

---

## Sources

- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://martinfowler.com/bliki/CircuitBreaker.html
