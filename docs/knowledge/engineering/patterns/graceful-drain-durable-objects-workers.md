# Graceful Drain Pattern for Durable Objects

2026-08-24 / example.com / production

---

## Symptom / Use-case

A Durable Object (DO) that holds in-flight WebSocket connections, pending writes, or in-progress transactions needs to be restarted or migrated. If the runtime evicts it abruptly—because of a deployment, a class rename migration, or an alarm that restarts the DO—inflight work is lost and clients get an unexpected disconnection or data corruption.

The graceful drain pattern gives a DO the ability to:
1. Signal itself to stop accepting new work.
2. Finish processing all current in-flight operations.
3. Flush buffered state to D1 or KV before the runtime closes it.

---

## Context

The Cloudflare Workers runtime can evict a Durable Object instance at any time. Key platform constraints:
- A DO instance handles one RPC/request at a time (sequential by design), except for WebSocket messages which are delivered concurrently per connection.
- The `alarm()` handler guarantees at-least-once execution, even across evictions. Use it as a flush trigger.
- DO storage (`this.ctx.storage`) is transactional and synchronous on the DO, so writes there are safe; D1 writes require error handling.

---

## Code sections

### 1. Durable Object state shape and drain flag

```typescript
// durable-objects/session-manager/src/SessionManager.ts

interface SessionState {
  draining: boolean;
  pendingWriteCount: number;
  bufferedEvents: Array<{ id: string; payload: unknown; ts: number }>;
}

export class SessionManager implements DurableObject {
  private state: DurableObjectState;
  private env: Env;
  private draining = false;
  private pendingWriteCount = 0;
  private bufferedEvents: SessionState['bufferedEvents'] = [];

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
    this.state.blockConcurrencyWhile(async () => {
      this.draining = (await this.state.storage.get<boolean>('draining')) ?? false;
      this.bufferedEvents = (await this.state.storage.get<SessionState['bufferedEvents']>('bufferedEvents')) ?? [];
      this.pendingWriteCount = (await this.state.storage.get<number>('pendingWriteCount')) ?? 0;
    });
  }
```

### 2. Accepting requests – reject when draining

```typescript
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/__drain' && request.method === 'POST') {
      return this.startDrain();
    }

    if (this.draining) {
      return new Response(
        JSON.stringify({ error: 'service_draining', retryAfterMs: 5000 }),
        { status: 503, headers: { 'Content-Type': 'application/json', 'Retry-After': '5' } }
      );
    }

    if (url.pathname === '/event' && request.method === 'POST') {
      return this.handleEvent(request);
    }

    return new Response('Not Found', { status: 404 });
  }

  private async startDrain(): Promise<Response> {
    this.draining = true;
    await this.state.storage.put('draining', true);
    await this.state.storage.setAlarm(Date.now() + 10_000);
    console.log('SessionManager: drain initiated');
    return new Response(JSON.stringify({ draining: true }), { headers: { 'Content-Type': 'application/json' } });
  }
```

### 3. Buffering in-flight events

```typescript
  private async handleEvent(request: Request): Promise<Response> {
    this.pendingWriteCount++;
    await this.state.storage.put('pendingWriteCount', this.pendingWriteCount);

    const body = await request.json<{ id: string; payload: unknown }>();
    try {
      const event = { id: body.id, payload: body.payload, ts: Date.now() };
      this.bufferedEvents.push(event);
      await this.state.storage.put('bufferedEvents', this.bufferedEvents);
      return new Response(JSON.stringify({ accepted: true, eventId: body.id }), {
        headers: { 'Content-Type': 'application/json' },
      });
    } finally {
      this.pendingWriteCount = Math.max(0, this.pendingWriteCount - 1);
      await this.state.storage.put('pendingWriteCount', this.pendingWriteCount);
    }
  }
```

### 4. Alarm handler – flush buffered state before eviction

```typescript
  async alarm(): Promise<void> {
    const pending = (await this.state.storage.get<number>('pendingWriteCount')) ?? 0;

    if (pending > 0) {
      console.warn(`SessionManager: ${pending} writes still pending, rescheduling alarm`);
      await this.state.storage.setAlarm(Date.now() + 3_000);
      return;
    }

    const events = (await this.state.storage.get<SessionState['bufferedEvents']>('bufferedEvents')) ?? [];
    if (events.length === 0) {
      console.log('SessionManager: nothing to flush, shutting down cleanly');
      await this.state.storage.deleteAll();
      return;
    }

    try {
      const stmts = events.map((e) =>
        this.env.DB.prepare(
          'INSERT INTO session_events (id, payload, recorded_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING'
        ).bind(e.id, JSON.stringify(e.payload), new Date(e.ts).toISOString())
      );
      await this.env.DB.batch(stmts);
      this.bufferedEvents = [];
      await this.state.storage.delete('bufferedEvents');
      await this.state.storage.deleteAll();
      console.log(`SessionManager: flushed ${events.length} events, drained`);
    } catch (err) {
      console.error('SessionManager: D1 flush failed, retrying', err);
      await this.state.storage.setAlarm(Date.now() + 5_000);
    }
  }
```

### 5. Deployment orchestration Worker – initiating drain before hot-swapping

```typescript
// workers/deploy-orchestrator/src/index.ts

interface Env {
  SESSION_MANAGER: DurableObjectNamespace;
  DEPLOY_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.headers.get('Authorization') !== `Bearer ${env.DEPLOY_SECRET}`) {
      return new Response('Unauthorized', { status: 401 });
    }
    const url = new URL(request.url);
    if (url.pathname !== '/orchestrate/drain' || request.method !== 'POST') {
      return new Response('Not Found', { status: 404 });
    }
    const body = await request.json<{ instanceIds: string[] }>();
    const results: Array<{ id: string; status: string }> = [];
    for (const id of body.instanceIds) {
      const stub = env.SESSION_MANAGER.get(env.SESSION_MANAGER.idFromName(id));
      try {
        const resp = await stub.fetch('https://internal/__drain', { method: 'POST' });
        results.push({ id, status: resp.ok ? 'draining' : 'error' });
      } catch {
        results.push({ id, status: 'unreachable' });
      }
    }
    return new Response(JSON.stringify({ results }), { headers: { 'Content-Type': 'application/json' } });
  },
};
```

### 6. Client-side retry on 503 Retry-After

```typescript
async function sendEventWithDrainRetry(endpoint: string, payload: unknown, maxRetries = 3): Promise<void> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const resp = await fetch(endpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    if (resp.ok) return;
    if (resp.status === 503) {
      const retryAfterSec = Number(resp.headers.get('Retry-After') ?? '5');
      if (attempt < maxRetries) { await new Promise((r) => setTimeout(r, retryAfterSec * 1_000)); continue; }
    }
    throw new Error(`Unexpected response ${resp.status} from ${endpoint}`);
  }
}
```

---

## Anti-patterns

- **Deleting DO storage without flushing.** Calling `deleteAll()` before D1 writes commit causes permanent data loss.
- **Setting only one alarm.** If D1 is temporarily unavailable during the alarm, the DO must reschedule before exiting `alarm()`.
- **Draining in the fetch handler.** Flushing synchronously inside `fetch()` blocks the event loop and exceeds CPU time limits. Use the alarm for bulk flush.
- **Trusting `pendingWriteCount` from memory alone.** Always back the counter in DO storage.
- **Not returning `Retry-After` to callers.** Without this header, clients may hammer the draining DO and delay the flush.

---

## Gotchas

- **Alarm delivery is at-least-once.** Flush logic in `alarm()` must be idempotent. Use `ON CONFLICT DO NOTHING` on D1 inserts.
- **`blockConcurrencyWhile` is synchronous from the caller's perspective.** Requests arriving while the constructor is blocked are queued automatically.
- **DO alarm timer resolution is approximately 1 second.** Do not rely on sub-second precision for the drain window.
- **Class rename migrations evict all instances immediately.** Trigger `/__drain` via CI before deploying a wrangler migration that renames the DO class.

---

## Verification

```bash
INSTANCE_ID="test-session-001"

# Send events
for i in 1 2 3; do
  curl -s -X POST https://my-worker.example.com/event \
    -H "Content-Type: application/json" -d "{\"id\": \"evt-$i\", \"payload\": {\"seq\": $i}}"
done

# Trigger drain
curl -s -X POST https://deploy-orchestrator.example.com/orchestrate/drain \
  -H "Authorization: Bearer $DEPLOY_SECRET" \
  -H "Content-Type: application/json" -d "{\"instanceIds\": [\"$INSTANCE_ID\"]}"

# Confirm 503 on subsequent requests
curl -s -o /dev/null -w "%{http_code}" -X POST https://my-worker.example.com/event -d '{"id":"after-drain","payload":{}}'
# Expected: 503

# Verify D1 contains flushed events
wrangler d1 execute orders-db --command "SELECT id, recorded_at FROM session_events ORDER BY recorded_at;"
```

---

## Related

- `distributed-lock-durable-objects.md`
- `temporal-pattern-workers-cron-alarms.md`
- `snapshot-durable-objects-versioning.md`
- `outbox-pattern-d1-reliable-publishing.md`

---

## Sources

- Cloudflare Durable Objects – Alarms API – https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare Durable Objects – Migrations – https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/
- Cloudflare Durable Objects – `blockConcurrencyWhile` – https://developers.cloudflare.com/durable-objects/api/state/#blockconcurrencywhile
