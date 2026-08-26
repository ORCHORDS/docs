# Workers Memory Leak Detection in Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Durable Object that handles WebSocket connections starts returning 500 errors after running for several hours. Memory usage climbs steadily from 5 MB at startup to 128 MB (the hard limit) over 6–8 hours, then the isolate is killed. Restarting the DO clears the issue temporarily, but it recurs on the same schedule. Request latency inside the DO degrades gradually as the heap grows, with GC pauses becoming noticeable above 80 MB. The problem does not reproduce in `wrangler dev` local mode.

## Context

Cloudflare Workers (including Durable Objects) run in V8 isolates with a **128 MB memory limit**. When a Worker or DO exceeds this limit, the isolate is terminated abruptly. For stateless Workers, this is a self-healing nuisance — the next request gets a fresh isolate. For **Durable Objects**, an OOM kill can happen mid-transaction, and the DO only recovers on the next incoming request or alarm. Long-lived DOs that hold open WebSocket connections, maintain in-memory caches, or accumulate event listeners are the most common victims of memory leaks.

## Solution

```typescript
import { Env } from './types';

// ─── Pattern 1: Monitoring memory usage ──────────────────────────────────────
// performance.measureUserAgentSpecificMemory() is available in Workers
// (when the Cross-Origin-Opener-Policy and Cross-Origin-Embedder-Policy
// headers are set, or in a Durable Object context where isolation is implicit).
// In practice, DOs can call it without the COOP/COEP headers.

export class MemoryAwareDO implements DurableObject {
  private state: DurableObjectState;
  private env: Env;
  // ❌ Leak source: unbounded Map with no eviction policy
  private sessionCache = new Map<string, { data: unknown; ts: number }>();
  // ❌ Leak source: accumulated event handlers with no cleanup
  private cleanupCallbacks: Array<() => void> = [];

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
    // Schedule periodic memory check via alarm
    this.scheduleMemoryCheck();
  }

  private async scheduleMemoryCheck(): Promise<void> {
    const existing = await this.state.storage.getAlarm();
    if (existing === null) {
      await this.state.storage.setAlarm(Date.now() + 60_000); // check every 60 s
    }
  }

  async alarm(): Promise<void> {
    await this.checkMemory();
    await this.evictStaleCache();
    // Reschedule
    await this.state.storage.setAlarm(Date.now() + 60_000);
  }

  private async checkMemory(): Promise<void> {
    // measureUserAgentSpecificMemory is non-standard but available in V8
    // workers context; TypeScript requires a cast.
    const perf = performance as unknown as {
      measureUserAgentSpecificMemory?: () => Promise<{ bytes: number }>
    };

    if (!perf.measureUserAgentSpecificMemory) return;

    try {
      const measurement = await perf.measureUserAgentSpecificMemory();
      const usedMB = measurement.bytes / (1024 * 1024);

      // Emit to Analytics Engine for trending
      (this.env as Env & { AE: AnalyticsEngineDataset }).AE?.writeDataPoint({
        blobs:   ['do-memory'],
        doubles: [usedMB],
        indexes: ['memory-monitor'],
      });

      // Proactive self-eviction before OOM kill at 128 MB
      if (usedMB > 100) {
        console.warn(`DO memory critical: ${usedMB.toFixed(1)} MB — initiating reset`);
        await this.gracefulReset();
      }
    } catch (_err) {
      // Not available in all environments — skip silently
    }
  }

  // ─── Pattern 2: Bounded cache with TTL eviction ───────────────────────────
  private async evictStaleCache(): Promise<void> {
    const MAX_ENTRIES = 500;
    const TTL_MS = 10 * 60 * 1000; // 10 minutes
    const now = Date.now();

    // Evict by TTL first
    for (const [key, entry] of this.sessionCache.entries()) {
      if (now - entry.ts > TTL_MS) this.sessionCache.delete(key);
    }

    // Evict by LRU if still over capacity (simplistic: evict oldest)
    if (this.sessionCache.size > MAX_ENTRIES) {
      const sortedKeys = [...this.sessionCache.entries()]
        .sort((a, b) => a[1].ts - b[1].ts)
        .map(([k]) => k);
      const toDelete = sortedKeys.slice(0, this.sessionCache.size - MAX_ENTRIES);
      for (const key of toDelete) this.sessionCache.delete(key);
    }
  }

  // ─── Pattern 3: Graceful reset strategy ──────────────────────────────────
  // Instead of letting the OOM killer terminate the DO mid-operation,
  // proactively flush in-memory state to durable storage and clear caches.
  private async gracefulReset(): Promise<void> {
    // 1. Persist any dirty in-memory state before clearing it
    const dirtyEntries: Record<string, unknown> = {};
    for (const [key, entry] of this.sessionCache.entries()) {
      dirtyEntries[`cache:${key}`] = entry.data;
    }
    if (Object.keys(dirtyEntries).length > 0) {
      await this.state.storage.put(dirtyEntries);
    }

    // 2. Clear the in-memory cache
    this.sessionCache.clear();

    // 3. Run all cleanup callbacks to release event listeners
    for (const cleanup of this.cleanupCallbacks) {
      try { cleanup(); } catch (_) { /* best-effort */ }
    }
    this.cleanupCallbacks = [];

    console.log('DO graceful reset complete — memory freed');
  }

  // ─── Pattern 4: WebSocket lifecycle and listener cleanup ─────────────────
  async fetch(request: Request): Promise<Response> {
    if (request.headers.get('Upgrade') === 'websocket') {
      return this.handleWebSocket(request);
    }
    return this.handleHTTP(request);
  }

  private async handleWebSocket(request: Request): Promise<Response> {
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);

    this.state.acceptWebSocket(server);
    return new Response(null, { status: 101, webSocket: client });
  }

  // DO WebSocket event handlers — called by the runtime, no manual addEventListener
  webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): void {
    // ❌ BAD: storing a reference to every received message
    // this.messageHistory.push({ ws, message });  // leaks ws reference + message data

    // ✅ GOOD: process and discard
    const data = typeof message === 'string' ? JSON.parse(message) : null;
    if (!data) return;
    // Process data inline, do not store references to ws or message
    void this.processMessage(ws, data);
  }

  webSocketClose(ws: WebSocket, code: number, reason: string): void {
    // DO Hibernation API: DO not hold references to closed WebSockets.
    // Remove any per-socket state stored in Maps keyed by ws object.
    // Instead, key by a stable session ID stored in the WebSocket's tag.
    const tag = this.state.getTags(ws)[0];
    if (tag) this.sessionCache.delete(tag);
  }

  webSocketError(ws: WebSocket, error: unknown): void {
    const tag = this.state.getTags(ws)[0];
    if (tag) this.sessionCache.delete(tag);
    console.error('WebSocket error on session', tag, error);
  }

  private async processMessage(ws: WebSocket, data: unknown): Promise<void> {
    // Process without storing ws reference
    ws.send(JSON.stringify({ echo: data, ts: Date.now() }));
  }

  private async handleHTTP(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const sessionId = url.searchParams.get('session');
    if (!sessionId) return new Response('Bad Request', { status: 400 });

    // ✅ Bounded cache put with TTL tracking
    this.sessionCache.set(sessionId, { data: { active: true }, ts: Date.now() });
    return Response.json({ status: 'ok', sessionId });
  }
}

// ─── Pattern 5: Detecting circular references ────────────────────────────────
// Circular references prevent GC. Detect them before storing objects.

function hasCircularReference(obj: unknown, seen = new WeakSet()): boolean {
  if (typeof obj !== 'object' || obj === null) return false;
  if (seen.has(obj)) return true;
  seen.add(obj);
  for (const value of Object.values(obj as Record<string, unknown>)) {
    if (hasCircularReference(value, seen)) return true;
  }
  return false;
}

function safeStore(cache: Map<string, unknown>, key: string, value: unknown): void {
  if (hasCircularReference(value)) {
    console.warn(`Refusing to store circular reference under key: ${key}`);
    return;
  }
  cache.set(key, value);
}

// ─── Pattern 6: Gradual DO eviction via namespace migration ──────────────────
// If a DO class has a persistent leak that cannot be patched immediately,
// force eviction by migrating to a new DO class name. All clients connecting
// to the new name get fresh isolates. Old DOs drain naturally as connections close.
//
// wrangler.toml:
// [[migrations]]
// tag = "v2-memory-fix"
// new_classes = ["RoomDOv2"]
// deleted_classes = ["RoomDO"]   # after all clients have migrated
//
// Router code:
export function getDoStub(
  env: Env & { ROOM_DO_V2: DurableObjectNamespace },
  roomId: string
): DurableObjectStub {
  // All new requests go to v2; old v1 DOs evict once their WebSockets close.
  const id = env.ROOM_DO_V2.idFromName(roomId);
  return env.ROOM_DO_V2.get(id);
}

// ─── Pattern 7: Heap snapshot comparison (diagnostic technique) ───────────────
// Cloudflare does not expose heap snapshots directly, but you can approximate
// the technique by logging object counts at periodic intervals.

class HeapSizeEstimator {
  private snapshots: Array<{ ts: number; cacheSize: number; listenerCount: number }> = [];

  snapshot(cacheSize: number, listenerCount: number): void {
    this.snapshots.push({ ts: Date.now(), cacheSize, listenerCount });
    // Keep only last 60 snapshots (60 minutes at 1/min)
    if (this.snapshots.length > 60) this.snapshots.shift();
  }

  isLeaking(): boolean {
    if (this.snapshots.length < 10) return false;
    const first = this.snapshots[0];
    const last = this.snapshots[this.snapshots.length - 1];
    const growthPerMinute = (last.cacheSize - first.cacheSize) / this.snapshots.length;
    // Alert if cache is growing by more than 5 entries/minute consistently
    return growthPerMinute > 5;
  }

  report(): string {
    const last = this.snapshots.at(-1);
    if (!last) return 'no data';
    return `cache=${last.cacheSize} listeners=${last.listenerCount} leaking=${this.isLeaking()}`;
  }
}
```

## Implementation Details

**`performance.measureUserAgentSpecificMemory()`** is a non-standard V8 API available in Workers isolates. It returns heap memory used by the current isolate in bytes. It is asynchronous (returns a promise) and has non-trivial overhead (~1–5 ms); call it at most once per minute via the alarm handler, not on every request.

**WebSocket hibernation vs open connections.** When a DO uses `this.state.acceptWebSocket()` (the Hibernation API), the isolate can be evicted between messages, releasing memory. On the next message, the isolate is restored from durable storage. If you use raw `WebSocketPair` without the Hibernation API, the isolate stays alive for the full lifetime of all open connections — the primary cause of long-lived memory accumulation.

**Bounded Map eviction.** The single most common leak in DO code is a `Map` used as a cache with no eviction policy. Every entry added during the DO's lifetime remains until the isolate is killed. Always set a maximum size and a TTL-based eviction strategy.

**DO alarm chaining for memory monitoring.** The alarm handler reschedules itself indefinitely. If the alarm is missed (DO was evicted), the next `fetch()` or `alarm()` invocation will see no pending alarm and should reschedule. Add null-check logic in the constructor to handle this case.

## Anti-patterns

- **Storing `WebSocket` object references in a `Map` keyed by the socket itself.** WebSocket objects cannot be garbage collected while referenced. Key by a stable ID (e.g. the session UUID stored as a WebSocket tag) and remove the entry in `webSocketClose`.
- **`addEventListener` without a corresponding `removeEventListener`.** Every listener added to a global or long-lived object that is never removed is a permanent leak. Prefer the DO Hibernation API event callbacks which are managed by the runtime.
- **Accumulating log lines in an in-memory array for batch shipping.** A log buffer that is never drained because the upstream is slow will grow unboundedly. Cap the buffer size and drop oldest entries when full.
- **Caching user-supplied data without a size limit.** An attacker or a bug can flood the cache with large payloads, triggering OOM faster.
- **Not testing with realistic connection lifetimes.** Local `wrangler dev` does not enforce the 128 MB limit and does not emulate DO eviction. Always stress-test long-lived DOs in a staging environment with production-level connection durations.

## Gotchas

- **DO OOM kill does not trigger `webSocketClose`.** When the isolate is killed due to OOM, in-flight WebSocket connections are dropped without the `webSocketClose` handler firing. Any cleanup logic there will not run. Use the Hibernation API to ensure state is flushed to durable storage between messages.
- **`this.state.storage.setAlarm()` is not guaranteed if the alarm handler itself OOMs.** If the alarm is the source of a memory spike (e.g. loading large data for processing), the DO may OOM before it reschedules. Use a try/finally block around the rescheduling call.
- **Memory is per-isolate, not per-DO-instance.** All DO instances of the same class that are colocated in the same Worker process share the same isolate — but in practice, each DO instance gets its own isolate on Cloudflare. Do not assume sharing.
- **V8 GC does not run predictably.** Memory may appear to plateau and then spike as GC is deferred. `measureUserAgentSpecificMemory()` reflects post-GC heap size after the promise resolves, not the current heap high-watermark.

## Verification

```typescript
// Load test a DO with WebSocket connections held for 30 minutes:
// npx autocannon --ws -c 20 -d 1800 wss://your-do-endpoint.example.com
//
// Monitor memory growth via Analytics Engine:
// SELECT
//   toStartOfMinute(timestamp) AS ts,
//   avg(double1) AS avg_mb,
//   max(double1) AS max_mb
// FROM workers_memory_monitor
// WHERE timestamp > now() - INTERVAL '2' HOUR
// GROUP BY ts ORDER BY ts
//
// Expected: avg_mb should plateau (bounded cache) rather than grow linearly.
// A linear growth slope > 1 MB/min indicates an active leak.

// Unit test for the eviction policy:
async function testCacheBoundary(): Promise<void> {
  const cache = new Map<string, { data: unknown; ts: number }>();
  const MAX = 500;
  for (let i = 0; i < MAX + 100; i++) {
    cache.set(`key-${i}`, { data: { i }, ts: Date.now() - i * 1000 });
  }
  // Apply eviction
  if (cache.size > MAX) {
    const toDelete = [...cache.entries()]
      .sort((a, b) => a[1].ts - b[1].ts)
      .slice(0, cache.size - MAX)
      .map(([k]) => k);
    for (const k of toDelete) cache.delete(k);
  }
  if (cache.size > MAX) throw new Error(`Cache exceeded bound: ${cache.size}`);
  console.log(`PASS: cache bounded at ${cache.size} entries`);
}
```

## Related

- `workers-memory-128mb-limit-oom-postmortem.md`
- `memory-leak-gradual-oom.md`
- `durable-objects-websocket-hibernation-migration-adr.md`
- `durable-objects-storage-transaction-atomicity-lesson.md`
- `durable-objects-alarm-delivery-guarantee-lesson.md`

## Sources

- Cloudflare Workers — Limits (memory): https://developers.cloudflare.com/workers/platform/limits/#memory
- Cloudflare Durable Objects — WebSocket Hibernation: https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- Cloudflare Durable Objects — Alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- W3C — `performance.measureUserAgentSpecificMemory()`: https://wicg.github.io/performance-measure-memory/
- V8 Blog — Memory Management: https://v8.dev/blog/trash-talk
