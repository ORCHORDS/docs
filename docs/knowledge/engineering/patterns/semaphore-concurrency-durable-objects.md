# Semaphore Concurrency Control with Durable Objects

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to cap the number of concurrent operations touching a shared resource — e.g.,
no more than 5 simultaneous heavy AI-inference calls, at most 3 concurrent writes to a
third-party API with a concurrency limit, or at most 1 import job per tenant at a time.
Workers run as massively parallel edge isolates; without coordination, thousands of
concurrent requests can all proceed simultaneously, overwhelming the downstream target.

A distributed semaphore built on a Durable Object serialises acquisition and release
through a single actor, providing an exact in-flight limit with queue-based waiting.

---

## Context

A semaphore is a counter that controls access to a bounded resource pool:

- **Acquire** — decrement the counter. If it would go below 0, block (or reject).
- **Release** — increment the counter and wake a waiter.

In a single-process app you implement this with `Atomics` or a mutex. In a distributed
system you need a single authoritative node. Cloudflare Durable Objects provide exactly
that: one JS actor per named shard, with serialised request processing.

Durable Objects' WebSocket hibernation API makes it cheap to hold open waiting
connections without consuming memory between messages.

---

## Architecture

```
Workers (N concurrent requests)
    │  acquire?
    ▼
┌───────────────────────────────────┐
│  SemaphoreDO (named per resource) │
│                                   │
│  permits: number  ← remaining     │
│  waiters: Queue<WebSocket>         │
│                                   │
│  acquire() → grant or enqueue     │
│  release() → grant to next waiter │
└───────────────────────────────────┘
```

---

## Implementation

### 1. Durable Object — the semaphore actor

```typescript
// SemaphoreDO.ts
interface AcquireRequest {
  action: "acquire";
}
interface ReleaseRequest {
  action: "release";
}
type SemaphoreMessage = AcquireRequest | ReleaseRequest;

export class SemaphoreDO implements DurableObject {
  private permits: number;
  private maxPermits: number;
  // Ordered list of WebSockets waiting for a permit
  private waiters: WebSocket[] = [];

  constructor(
    private readonly ctx: DurableObjectState,
    private readonly env: unknown,
  ) {
    // Default — callers pass ?max= on first acquire to set it
    this.maxPermits = 5;
    this.permits = this.maxPermits;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const action = url.searchParams.get("action");

    // WebSocket upgrade — caller holds the socket open until the semaphore grants
    if (action === "acquire") {
      const max = parseInt(url.searchParams.get("max") ?? String(this.maxPermits), 10);
      if (max !== this.maxPermits) {
        // Allow re-configuration on the first call
        this.maxPermits = max;
        this.permits = Math.min(this.permits, max);
      }

      const { 0: client, 1: server } = new WebSocketPair();
      this.ctx.acceptWebSocket(server, ["semaphore-waiter"]);

      if (this.permits > 0) {
        this.permits--;
        // Grant immediately
        server.send(JSON.stringify({ granted: true, remaining: this.permits }));
      } else {
        // Enqueue — will be granted when a release arrives
        this.waiters.push(server);
        server.send(JSON.stringify({ granted: false, queued: this.waiters.length }));
      }

      return new Response(null, { status: 101, webSocket: client });
    }

    if (action === "release") {
      this.release();
      return Response.json({ ok: true, remaining: this.permits });
    }

    if (action === "status") {
      return Response.json({
        permits: this.permits,
        maxPermits: this.maxPermits,
        waiters: this.waiters.length,
      });
    }

    return new Response("Unknown action", { status: 400 });
  }

  // Called when a WebSocket closes — release implicitly if the caller was granted
  webSocketClose(ws: WebSocket, code: number): void {
    // Remove from waiters queue if the caller disconnects before being granted
    const idx = this.waiters.indexOf(ws);
    if (idx !== -1) {
      this.waiters.splice(idx, 1);
      return; // was waiting, never granted — no release needed
    }
    // If it was granted and closed without releasing, release now
    this.release();
  }

  webSocketError(ws: WebSocket): void {
    this.webSocketClose(ws, 1011);
  }

  private release(): void {
    if (this.waiters.length > 0) {
      const next = this.waiters.shift()!;
      // Grant to the next waiter — permits stay at 0
      next.send(JSON.stringify({ granted: true, remaining: 0 }));
    } else {
      this.permits = Math.min(this.permits + 1, this.maxPermits);
    }
  }
}
```

### 2. Client helper — acquire/release from a Worker

```typescript
// semaphore-client.ts
interface SemaphoreOptions {
  name: string;         // semaphore name — maps to DO id
  maxPermits?: number;  // only matters on first ever acquire
  timeoutMs?: number;   // how long to wait before giving up
}

interface AcquireResult {
  release: () => void;
}

export async function acquireSemaphore(
  ns: DurableObjectNamespace,
  opts: SemaphoreOptions,
): Promise<AcquireResult> {
  const id = ns.idFromName(opts.name);
  const stub = ns.get(id);
  const params = new URLSearchParams({ action: "acquire" });
  if (opts.maxPermits) params.set("max", String(opts.maxPermits));

  // Open a WebSocket to the DO and wait for the grant message
  const upgradeRes = await stub.fetch(`https://internal/semaphore?${params}`, {
    headers: { Upgrade: "websocket" },
  });

  const ws = upgradeRes.webSocket;
  if (!ws) throw new Error("Failed to open semaphore WebSocket");
  ws.accept();

  await new Promise<void>((resolve, reject) => {
    const timeout = opts.timeoutMs
      ? setTimeout(() => {
          ws.close(1000, "timeout");
          reject(new Error(`Semaphore '${opts.name}' acquire timed out after ${opts.timeoutMs} ms`));
        }, opts.timeoutMs)
      : null;

    ws.addEventListener("message", (evt) => {
      const msg = JSON.parse(evt.data as string) as { granted: boolean };
      if (msg.granted) {
        if (timeout) clearTimeout(timeout);
        resolve();
      }
      // If not granted yet, keep waiting — DO will push a second message when granted
    });

    ws.addEventListener("error", () => {
      if (timeout) clearTimeout(timeout);
      reject(new Error("Semaphore WebSocket error"));
    });
  });

  return {
    release: () => {
      // Closing the socket triggers webSocketClose on the DO, which calls release()
      ws.close(1000, "done");
    },
  };
}
```

### 3. Using the semaphore in a Worker handler

```typescript
// index.ts
import { acquireSemaphore } from "./semaphore-client";

interface Env {
  SEMAPHORE: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    let permit: { release: () => void } | null = null;
    try {
      // At most 3 concurrent heavy operations per "ai-inference" resource
      permit = await acquireSemaphore(env.SEMAPHORE, {
        name: "ai-inference",
        maxPermits: 3,
        timeoutMs: 10_000, // queue for up to 10 s, then 429
      });

      // --- critical section ---
      const result = await runHeavyInference(request);
      // --- end critical section ---

      return Response.json({ result });
    } catch (err) {
      if (String(err).includes("timed out")) {
        return Response.json(
          { error: "Server busy, try again later" },
          { status: 429, headers: { "Retry-After": "5" } },
        );
      }
      throw err;
    } finally {
      permit?.release();
    }
  },
};

async function runHeavyInference(_req: Request): Promise<string> {
  // Simulate work
  await new Promise(r => setTimeout(r, 500));
  return "inference result";
}
```

### 4. Per-tenant semaphore (one semaphore per tenant)

```typescript
const tenantId = request.headers.get("X-Tenant-Id") ?? "global";
const permit = await acquireSemaphore(env.SEMAPHORE, {
  name: `import-job:${tenantId}`,
  maxPermits: 1,   // only 1 concurrent import per tenant
  timeoutMs: 0,    // fail fast — don't queue
});
```

---

## Anti-patterns

- **Using KV for the semaphore counter** — KV is eventually consistent; two Workers
  can both read `permits = 1`, both decrement to `0`, and both proceed. The Durable
  Object model is required for strong consistency.
- **Not releasing on error** — always use `try/finally` to call `release()`. Leaked
  permits permanently reduce available concurrency.
- **Shared semaphore name across unrelated resources** — keep names scoped to the
  actual resource. `"global"` is an anti-pattern unless all resources share the limit.
- **Very high `maxPermits`** — a semaphore with 500 permits provides little protection.
  Tune `maxPermits` to the actual downstream concurrency limit.
- **Infinite queue (no `timeoutMs`)** — a thundering herd will pile up thousands of
  waiters in the DO. Set a timeout and return `429` when exceeded.

---

## Gotchas

- The Durable Object WebSocket API requires `this.ctx.acceptWebSocket(server)` with
  the hibernation API. The older `this.state.acceptWebSocket` syntax is deprecated.
- `webSocketClose` fires even on clean closes. If you track which sockets are
  "granted" vs. "waiting", update the tracking before closing to avoid double-release.
- Workers on the free plan cannot hold WebSocket connections longer than the 30-second
  CPU time limit. For long-running critical sections use a polling-based approach
  (acquire returns a token, check the token on a timer) instead of a held WebSocket.
- Durable Objects are single-threaded but process each `fetch()` call concurrently
  at the microtask level. The semaphore state mutations above are synchronous and
  therefore safe — but any `await` between read and write would require a mutex.

---

## Verification

```bash
# Fire 10 concurrent requests, observe that at most 3 run in parallel
for i in $(seq 1 10); do
  curl -s https://api.example.com/heavy &
done
wait
# Check DO status
curl https://semaphore-do.internal/semaphore?action=status
# {"permits":3,"maxPermits":3,"waiters":0}
```

Load test with `k6`:

```js
import http from "k6/http";
import { check } from "k6";
export const options = { vus: 20, duration: "15s" };
export default function () {
  const res = http.get("https://api.example.com/heavy");
  check(res, { "status 200 or 429": r => r.status === 200 || r.status === 429 });
}
```

---

## Related

- `distributed-lock-durable-objects.md` — mutual exclusion (semaphore with maxPermits=1)
- `lease-based-concurrency-d1.md` — DB-backed concurrency control without DOs
- `request-batching-durable-objects.md` — batching incoming requests in a DO actor
- `bulkhead-pattern-workers-subrequests.md` — partitioning resource pools

---

## Sources

- Cloudflare Durable Objects WebSocket Hibernation — developers.cloudflare.com/durable-objects/api/websockets/
- Dijkstra, E.W. (1965) — "Cooperating Sequential Processes"
- "Semaphore (programming)" — en.wikipedia.org/wiki/Semaphore_(programming)
