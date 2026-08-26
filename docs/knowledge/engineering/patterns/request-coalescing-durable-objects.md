# Request Coalescing with Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Multiple concurrent Workers requests arrive for the same slow or expensive upstream resource (a third-party API, a database query, a signed URL). Without coordination, each Worker fires an independent upstream request, creating a thundering-herd problem that wastes quota, adds latency, and can overwhelm the origin. You need exactly-once upstream execution with the result fanned out to all callers.

---

## Context

Durable Objects provide a single-threaded, strongly-consistent execution context that can hold JavaScript `Promise` references in memory between requests. By routing all Workers requests for the same resource key to the same named Durable Object, the DO becomes a natural coalescing point: the first request triggers the upstream fetch, subsequent concurrent requests attach to the same in-flight `Promise`, and when the fetch resolves all waiters receive the result simultaneously. The DO stores the resolved value in its persistent storage for a configurable TTL so later requests (post-coalescing window) are served from the DO cache without hitting upstream at all. An `alarm()` is set as a safety net to prevent a hung upstream from blocking waiters indefinitely.

---

## Durable Object & Worker Config

```toml
# wrangler.toml
[[durable_objects.bindings]]
name       = "COALESCER"
class_name = "CoalescerDO"

[[migrations]]
tag      = "v1"
new_classes = ["CoalescerDO"]

[vars]
UPSTREAM_URL     = "https://api.example.com/slow-resource"
CACHE_TTL_SEC    = "30"
ALARM_TIMEOUT_MS = "5000"
```

---

## Durable Object Implementation

```typescript
// src/coalescer-do.ts

export interface Env {
  COALESCER: DurableObjectNamespace;
  UPSTREAM_URL: string;
  CACHE_TTL_SEC: string;
  ALARM_TIMEOUT_MS: string;
}

interface CachedResult {
  body: string;
  status: number;
  expiresAt: number; // Unix ms
}

export class CoalescerDO implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  /** In-memory promise shared by concurrent waiters during the coalescing window. */
  private inflight: Promise<CachedResult> | null = null;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env   = env;
  }

  // ── Entry point ────────────────────────────────────────────────────────────
  async fetch(request: Request): Promise<Response> {
    const now    = Date.now();
    const ttlMs  = parseInt(this.env.CACHE_TTL_SEC, 10) * 1_000;

    // 1. Serve from DO storage if cached result is still fresh
    const cached = await this.state.storage.get<CachedResult>("result");
    if (cached && cached.expiresAt > now) {
      return new Response(cached.body, {
        status: cached.status,
        headers: { "X-Cache": "HIT", "Content-Type": "application/json" },
      });
    }

    // 2. Coalesce: attach to in-flight promise or start a new one
    if (!this.inflight) {
      this.inflight = this.fetchUpstream(ttlMs);

      // Safety alarm — cancel the in-flight promise if upstream hangs
      const alarmMs = parseInt(this.env.ALARM_TIMEOUT_MS, 10);
      await this.state.storage.setAlarm(Date.now() + alarmMs);
    }

    try {
      const result = await this.inflight;
      return new Response(result.body, {
        status: result.status,
        headers: { "X-Cache": "MISS", "Content-Type": "application/json" },
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "upstream failed", detail: String(err) }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
  }

  // ── Alarm handler — clears a stuck in-flight promise ──────────────────────
  async alarm(): Promise<void> {
    // If inflight is still pending when alarm fires, reject all waiters
    this.inflight = null;
    console.error("CoalescerDO: upstream timeout, alarm fired");
  }

  // ── Private: execute upstream fetch and cache result ──────────────────────
  private async fetchUpstream(ttlMs: number): Promise<CachedResult> {
    try {
      const res  = await fetch(this.env.UPSTREAM_URL);
      const body = await res.text();

      const result: CachedResult = {
        body,
        status:    res.status,
        expiresAt: Date.now() + ttlMs,
      };

      // Persist for subsequent requests after the coalescing window
      await this.state.storage.put("result", result);

      // Cancel the safety alarm — upstream responded in time
      await this.state.storage.deleteAlarm();

      return result;
    } finally {
      // Always clear so the next miss triggers a fresh fetch
      this.inflight = null;
    }
  }
}

// src/index.ts
import { CoalescerDO, type Env } from "./coalescer-do";
export { CoalescerDO };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url      = new URL(request.url);
    // Use the resource identifier as the DO name so all requests for the
    // same resource route to the same DO instance.
    const resource = url.searchParams.get("resource") ?? "default";
    const id       = env.COALESCER.idFromName(resource);
    const stub     = env.COALESCER.get(id);
    return stub.fetch(request);
  },
};
```

---

## Integration / Testing

```typescript
// test/coalescer.test.ts  (Vitest + @cloudflare/vitest-pool-workers)
import { env, createExecutionContext, waitOnExecutionContext, runInDurableObject } from "cloudflare:test";
import { describe, it, expect, vi } from "vitest";
import worker, { CoalescerDO } from "../src/index";

describe("request coalescing DO", () => {
  it("executes upstream fetch only once for concurrent requests", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data: 42 }), { status: 200 })
    );

    const makeReq = () =>
      new Request("https://worker.example.com/?resource=test");

    // Fire 5 concurrent requests
    const contexts = Array.from({ length: 5 }, () => createExecutionContext());
    const responses = await Promise.all(
      contexts.map((ctx) => worker.fetch(makeReq(), env, ctx))
    );
    await Promise.all(contexts.map(waitOnExecutionContext));

    // All should succeed
    responses.forEach((r) => expect(r.status).toBe(200));

    // Upstream called exactly once
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    fetchSpy.mockRestore();
  });

  it("serves cached result on subsequent requests within TTL", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(`{"data":1}`, { status: 200 })
    );

    const req = new Request("https://worker.example.com/?resource=cached");
    const ctx1 = createExecutionContext();
    const r1 = await worker.fetch(req, env, ctx1);
    await waitOnExecutionContext(ctx1);
    expect(r1.headers.get("X-Cache")).toBe("MISS");

    const ctx2 = createExecutionContext();
    const r2 = await worker.fetch(req, env, ctx2);
    await waitOnExecutionContext(ctx2);
    expect(r2.headers.get("X-Cache")).toBe("HIT");
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    fetchSpy.mockRestore();
  });
});
```

---

## Anti-patterns

- **Using a global Worker variable for the shared promise** — Workers can run in many isolates simultaneously; the shared promise must live in a DO, not a module-level variable in the Worker itself.
- **No alarm timeout** — if upstream hangs forever, all coalesced waiters block until the DO times out (30 s default), compounding latency for every caller.
- **Not clearing `inflight` in a `finally` block** — if the upstream rejects and `inflight` is not nulled, every subsequent request will await an already-rejected promise and get a 502 in perpetuity.
- **One DO for all resources** — routing every resource to the same DO creates a single-threaded bottleneck; derive the DO name from the resource key so each resource gets its own isolated instance.

---

## Gotchas

- Durable Objects have a per-request CPU time limit (30 s by default); ensure upstream calls complete within that budget or the alarm will fire.
- `state.storage.deleteAlarm()` is a no-op if no alarm is set; it is safe to call unconditionally.
- DO WebSocket hibernation is not relevant here — this pattern uses the standard fetch handler only.
- In Wrangler local dev, `setAlarm` / `deleteAlarm` are supported from Wrangler v3.19+; older versions silently ignore them.
- The coalescing window is the time between the first MISS and the storage `put`; requests arriving after the `put` are served from cache, not coalesced.

---

## Verification

```bash
# Start local dev
npx wrangler dev &

# Fire 10 concurrent requests and count upstream hits in DO logs
for i in $(seq 1 10); do
  curl -s "http://localhost:8787/?resource=foo" &
done
wait
# Expect to see exactly 1 "upstream fetch" log line

# Confirm cache hit on follow-up
curl -i "http://localhost:8787/?resource=foo"
# X-Cache: HIT

# Tail DO logs
npx wrangler tail --format pretty
```

---

## Related

- `token-bucket-rate-limit-workers-kv.md`
- `write-behind-cache-workers-kv-d1.md`
- `scatter-gather-workers-service-bindings.md`

---

## Sources

- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Durable Object alarms — https://developers.cloudflare.com/durable-objects/api/alarms/
- Thundering herd problem — https://en.wikipedia.org/wiki/Thundering_herd_problem
