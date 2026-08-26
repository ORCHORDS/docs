# Durable Object Hibernation Wake-Up Latency Debugging

2026-08-24 / example.com / production

---

## Symptom / Use-case

A Durable Object (DO) that has been idle for several minutes suddenly receives an incoming request and takes 200–800 ms longer than expected before its handler begins executing. The object is not restarting from scratch (no constructor logs), yet the first `fetch()` or alarm invocation after a quiet period is noticeably slower than subsequent requests in the same active window.

This manifests as:
- Tail latency spikes on DO-backed WebSocket connections after a period of silence
- Alarm handlers appearing to "slip" by hundreds of milliseconds past their scheduled time
- Health-check requests to a DO that was recently active returning with unexpectedly high TTFB

---

## Context

Cloudflare runs Durable Objects on isolated V8 isolates. When a DO receives no traffic for a period the runtime may place the isolate into **hibernation** — a low-cost suspended state where the JS heap is frozen but not evicted. On the next incoming event the runtime must:

1. Resume the isolate from the frozen snapshot
2. Restore the WebSocket attachment map (if using WebSocket Hibernation API)
3. Re-hydrate any state that was checkpointed

Hibernation is **distinct from eviction**. After eviction the constructor runs again. After hibernation wake-up the constructor does _not_ run; `webSocketMessage` / `webSocketClose` / `alarm` handlers resume directly. The cold path through the hibernation wake-up is largely invisible in Cloudflare's dashboard — it does not appear as CPU time, it appears as wall-clock latency between the event being enqueued and your handler receiving control.

Key facts:
- Hibernation occurs after roughly 10 seconds of total inactivity (undocumented; empirically observed)
- WebSocket Hibernation API (`acceptWebSocket`, `getWebSockets`) is **required** to survive hibernation with open sockets; classic event-listener sockets are closed on hibernation
- `alarm()` scheduling is unaffected by hibernation but the handler may wake a hibernated isolate
- `ctx.storage.get()` inside a cold wake adds another async round-trip on top of the resume latency

---

## Diagnosing the Wake-Up Path

### Step 1 — Add a high-resolution timing breadcrumb at handler entry

```typescript
// src/durable-object.ts
export class MyDurableObject implements DurableObject {
  private lastWakeTs: number = Date.now();

  async fetch(request: Request): Promise<Response> {
    const now = Date.now();
    const gapMs = now - this.lastWakeTs;
    this.lastWakeTs = now;

    // Emit to Analytics Engine for later analysis
    this.env.ANALYTICS.writeDataPoint({
      blobs: [request.url, this.ctx.id.toString()],
      doubles: [gapMs],
      indexes: ['do-wake-gap'],
    });

    // Large gap = likely woke from hibernation
    if (gapMs > 5_000) {
      console.log(`[DO wake] id=${this.ctx.id.name} gap=${gapMs}ms — probable hibernation resume`);
    }

    return this.handleRequest(request);
  }
}
```

### Step 2 — Measure wall-clock from the calling Worker

```typescript
// src/worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const stub = env.MY_DO.get(env.MY_DO.idFromName('singleton'));

    const t0 = performance.now();
    const response = await stub.fetch(request);
    const elapsed = performance.now() - t0;

    // Log the round-trip including wake overhead
    console.log(`DO round-trip: ${elapsed.toFixed(1)}ms status=${response.status}`);
    return response;
  },
};
```

### Step 3 — Isolate serialization cost from wake cost

```typescript
// Inside the DO — split storage reads away from handler entry
export class MyDurableObject implements DurableObject {
  private cache: Map<string, unknown> = new Map();
  private cacheWarmedAt = 0;

  private async ensureCache(): Promise<void> {
    if (this.cache.size > 0) return; // already warm in this isolate lifetime
    const t0 = performance.now();
    const all = await this.ctx.storage.list();
    all.forEach((v, k) => this.cache.set(k, v));
    console.log(`[DO cache warm] ${all.size} keys in ${(performance.now() - t0).toFixed(1)}ms`);
    this.cacheWarmedAt = Date.now();
  }

  async fetch(request: Request): Promise<Response> {
    await this.ensureCache(); // pays cost once per isolate lifetime
    // ... rest of handler
    return new Response('ok');
  }
}
```

### Step 4 — Check for accidental blocking in `webSocketMessage`

```typescript
// BAD — synchronous JSON.parse of a large payload blocks the isolate thread
// during wake, delaying all other pending messages
export class BadDurableObject implements DurableObject {
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const data = JSON.parse(message as string); // can be 10s of KB
    const result = await this.ctx.storage.get(data.key);
    ws.send(JSON.stringify(result));
  }
}

// GOOD — parse inside a microtask boundary, keep handler entry lightweight
export class GoodDurableObject implements DurableObject {
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    // Defer heavy parse until after the event loop tick
    await Promise.resolve();
    const data = JSON.parse(message as string);
    const result = await this.ctx.storage.get(data.key);
    ws.send(JSON.stringify(result));
  }
}
```

### Step 5 — Instrument alarm scheduling drift

```typescript
export class AlarmDurableObject implements DurableObject {
  async alarm(): Promise<void> {
    const scheduledAt = await this.ctx.storage.get<number>('nextAlarmTarget') ?? Date.now();
    const driftMs = Date.now() - scheduledAt;

    console.log(`[alarm] drift=${driftMs}ms — ${driftMs > 200 ? 'HIBERNATION WAKE' : 'normal'}`);

    // Reschedule
    const next = Date.now() + 30_000;
    await this.ctx.storage.put('nextAlarmTarget', next);
    await this.ctx.storage.setAlarm(next);
  }
}
```

### Step 6 — Use the WebSocket Hibernation API to avoid socket drops

```typescript
export class HibernationSafeDO implements DurableObject {
  constructor(private ctx: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get('Upgrade') === 'websocket') {
      const pair = new WebSocketPair();
      // acceptWebSocket persists through hibernation — do not use ws.accept()
      this.ctx.acceptWebSocket(pair[1]);
      return new Response(null, { status: 101, webSocket: pair[0] });
    }
    return new Response('not a websocket', { status: 400 });
  }

  // Called after hibernation wake — no constructor re-run
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    ws.send(`echo: ${message}`);
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    ws.close(code, reason);
  }
}
```

---

## Anti-patterns

- **Storing latency-sensitive state only in `this.*` fields** — these survive within an isolate lifetime but are gone after eviction; misreading a stale zero-value after wake leads to incorrect gap measurements.
- **Calling `ctx.storage.get()` at the top of every handler** — each call is a synchronous-looking async I/O round-trip. After a hibernation wake the first storage call has additional latency; batch into `storage.list()` or cache aggressively.
- **Using `ws.accept()` (EventTarget API) for long-lived WebSockets** — the runtime will close these sockets when the isolate hibernates. Switch to `ctx.acceptWebSocket()`.
- **Ignoring the gap between scheduling an alarm and its actual firing** — alarms can fire up to ~500 ms late on a hibernated isolate; do not use alarm scheduling as a precise ticker.

---

## Gotchas

- Hibernation wake-up latency does **not** appear in `cpuTime` metrics — it is infrastructure overhead, not your JS execution time.
- A DO with an open WebSocket managed via the Hibernation API **will not be evicted** while the socket is open, but it **can still be hibernated**; messages queued during hibernation are delivered on wake.
- `ctx.storage.put()` calls inside a handler complete transactionally with the response — writes are not flushed until after the handler returns. A crash mid-handler does not leave partial writes.
- The `constructor` is only re-invoked after full eviction (memory pressure or platform maintenance), not after hibernation. Code that relies on constructor side-effects for every "startup" will miss the hibernation case.
- `performance.now()` inside a DO reflects the isolate's clock; compare against `Date.now()` for wall-clock correlation when measuring wake overhead.

---

## Verification

1. Deploy with `console.log` wake-gap breadcrumbs, then idle the DO for 30 seconds.
2. Trigger a request and observe the log line — `gap` should be > 5 000 ms; verify latency spike in Workers Trace.
3. Make three back-to-back requests immediately after — gaps drop to < 50 ms, confirming the isolate is now hot.
4. Run `wrangler tail --format=pretty` and filter on `[DO wake]` to build a histogram of wake frequencies.
5. Add an Analytics Engine dataset and chart `doubles[0]` (gap) over time; spikes coinciding with alarm drift confirm hibernation is the root cause.

---

## Related

- `durable-object-heartbeat-platform-liveness-monitoring.md`
- `workers-kv-cold-read-performance.md`
- `worker-memory-limit-exceeded.md`

---

## Sources

- Cloudflare Durable Objects — WebSocket Hibernation API: https://developers.cloudflare.com/durable-objects/api/websockets/
- Cloudflare Durable Objects — Alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare Durable Objects — Transactional Storage: https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/
- Cloudflare Workers Trace Events: https://developers.cloudflare.com/workers/observability/logging/workers-trace-events/
