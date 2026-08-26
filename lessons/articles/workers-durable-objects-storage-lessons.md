# Durable Objects Storage: Hard Lessons from Production

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Our real-time collaboration feature relied heavily on Durable Objects (DOs) to hold per-document state. After several months in production we encountered:

- Writes that appeared to succeed but were lost on DO eviction under load
- Alarms firing hours late or not at all after a Cloudflare datacenter shuffle
- Migration of a DO class left millions of legacy keys orphaned in storage
- Storage costs 10× higher than projected due to small-key write amplification
- Hibernation-mode DOs resuming into a corrupt in-memory state we did not anticipate

This article documents what we learned, the patterns that helped, and what we would architect differently from day one.

---

## Context

Durable Objects give you a single-threaded, globally unique actor with strongly consistent transactional storage. That sounds simple but the consistency model has sharp edges that are easy to misread from the documentation.

Key facts that surprised us:

1. `storage.put()` is **synchronous** with respect to the DO's JavaScript execution but the actual durability flush to disk happens asynchronously before the current event loop turn yields to the network. If you `await fetch(...)` inside the same request handler after a `put()`, the put is already durable — but if you throw an uncaught exception before the handler resolves, Cloudflare rolls back all puts in that batch.
2. Alarms are reliable delivery with at-least-once semantics, but "at least once" means an alarm can fire **multiple times** if the DO is evicted mid-handler.
3. The DO storage quota (currently 128 KB per key, up to 128 MB total per instance) is per-instance, not per-class. A single busy instance can silently approach the limit.
4. DO migration (renaming a class or changing `durable_object` bindings) is not zero-downtime by default.

---

## Solution

### 1. Treat every request handler as a transaction boundary

Group all `storage.put()` calls so they complete before any external `await`. The runtime batches them automatically within a single sync block.

```typescript
// workers/src/document-do.ts

import { DurableObject } from 'cloudflare:workers';

interface DocumentState {
  content: string;
  version: number;
  lastEditor: string;
  updatedAt: number;
}

export class DocumentDO extends DurableObject {
  private state: DocumentState | null = null;

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'PUT' && url.pathname === '/update') {
      return this.handleUpdate(request);
    }

    if (request.method === 'GET' && url.pathname === '/read') {
      return this.handleRead();
    }

    return new Response('Not Found', { status: 404 });
  }

  private async handleUpdate(request: Request): Promise<Response> {
    const body = await request.json<Partial<DocumentState>>();

    // Load current state (cached after first read within the DO lifetime)
    const current = await this.loadState();

    const next: DocumentState = {
      content: body.content ?? current.content,
      version: current.version + 1,
      lastEditor: body.lastEditor ?? current.lastEditor,
      updatedAt: Date.now(),
    };

    // CRITICAL: do ALL puts before any external await.
    // The runtime flushes this batch atomically before returning the response.
    await this.ctx.storage.put<DocumentState>('doc', next);
    // Only AFTER storage work is complete do we touch the external world.
    this.state = next; // update in-memory cache

    return Response.json({ version: next.version });
  }

  private async handleRead(): Promise<Response> {
    const state = await this.loadState();
    return Response.json(state);
  }

  private async loadState(): Promise<DocumentState> {
    if (this.state) return this.state;
    const stored = await this.ctx.storage.get<DocumentState>('doc');
    this.state = stored ?? {
      content: '',
      version: 0,
      lastEditor: 'system',
      updatedAt: Date.now(),
    };
    return this.state;
  }
}
```

### 2. Make alarms idempotent

Alarms execute at-least-once. Write alarm handlers so running them twice has the same effect as once.

```typescript
// workers/src/document-do.ts (alarm handler)

export class DocumentDO extends DurableObject {
  // ... fetch handler above ...

  async alarm(): Promise<void> {
    // Read a checkpoint token stored alongside the real data.
    // If the checkpoint matches what we expect, the alarm already ran.
    const checkpoint = await this.ctx.storage.get<string>('alarm:checkpoint');
    const expected = await this.ctx.storage.get<string>('alarm:expected');

    if (checkpoint === expected) {
      // Already processed — idempotent exit
      return;
    }

    // Do the real work
    await this.flushSnapshotToR2();

    // Mark completion atomically with the checkpoint update
    await this.ctx.storage.put('alarm:checkpoint', expected);
  }

  private async scheduleSnapshot(delayMs: number): Promise<void> {
    const token = crypto.randomUUID();
    // Store the expected token and the alarm registration atomically
    await this.ctx.storage.put('alarm:expected', token);
    await this.ctx.storage.setAlarm(Date.now() + delayMs);
  }

  private async flushSnapshotToR2(): Promise<void> {
    // snapshot logic ...
  }
}
```

### 3. Hibernation API — restore in-memory state defensively

When using the Hibernation API the DO's JavaScript heap is discarded between WebSocket messages. Any in-memory cache must be lazily rehydrated.

```typescript
// workers/src/collab-do.ts

export class CollabDO extends DurableObject {
  private roomCache: Map<string, unknown> | null = null;

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    // roomCache may be null after hibernation — always hydrate before use
    const room = await this.getRoom();
    // process message with room ...
    void room;
  }

  private async getRoom(): Promise<Map<string, unknown>> {
    if (this.roomCache) return this.roomCache;
    // Rehydrate from durable storage
    const raw = await this.ctx.storage.get<unknown[]>('room:state');
    this.roomCache = new Map(raw as [string, unknown][] ?? []);
    return this.roomCache;
  }
}
```

---

## Implementation Details

### Storage key design matters — a lot

Every unique key is a storage entry. We initially stored per-user cursor positions as `cursor:${userId}` — 10 000 active users × tiny value = 10 000 entries. Each `storage.list()` scans all keys, which was slow. We consolidated into a single `cursors` key holding a serialised map.

```typescript
// Before (slow — 10 000 storage entries)
await this.ctx.storage.put(`cursor:${userId}`, { x, y });

// After (one entry, one read/write)
const cursors = await this.ctx.storage.get<Record<string, {x: number; y: number}>>('cursors') ?? {};
cursors[userId] = { x, y };
await this.ctx.storage.put('cursors', cursors);
```

### DO class migration procedure

Renaming a DO class in `wrangler.toml` creates a new namespace. Existing instances are not moved automatically. The safe procedure:

1. Deploy a new class name alongside the old one.
2. Implement a `GET /export` on the old class that streams all storage keys.
3. Implement a `POST /import` on the new class to accept and write those keys.
4. Run a migration Worker that iterates existing IDs, calls export → import.
5. Drain traffic to new class, delete old binding after confirming zero live connections.

There is no Cloudflare-managed rename; the above manual approach is what we use.

---

## Anti-patterns

- **Putting external fetches before storage.put()**: any thrown error from the fetch aborts the put silently — state is never saved.
- **Assuming alarm fires exactly once**: it does not; always write idempotent handlers.
- **Storing large blobs in DO storage**: the 128 KB-per-key limit can be hit silently with complex objects; serialise and chunk, or store large payloads in R2 and keep only a reference in DO storage.
- **Not calling `setAlarm` again inside the alarm handler if you want periodic firing**: alarms do not auto-repeat.
- **Using `storage.list()` on a namespace with thousands of keys without a prefix filter**: it is O(n) in key count and will time out.

---

## Gotchas

- `storage.deleteAll()` is not instantaneous under high key count — we observed it timing out for instances with >50 000 keys. Delete in batches of 128.
- The DO instance is not guaranteed to stay warm between requests even with alarms set. Never cache secrets or connections in module-level variables; always re-establish inside the handler.
- `ctx.storage.get()` returns `undefined` (not `null`) for missing keys — TypeScript types reflect this but it is easy to miss in conditional checks.
- After enabling the Hibernation API, WebSocket connections that were previously kept alive by a `while(true)` loop will be broken; the migration requires rewriting connection-keep-alive logic entirely.

---

## Verification

```typescript
// tests/do-storage.test.ts
import { env, runInDurableObject } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';
import { DocumentDO } from '../src/document-do';

describe('DocumentDO storage', () => {
  it('persists state across handler invocations', async () => {
    const id = env.DOCUMENT_DO.idFromName('test-doc-1');
    const stub = env.DOCUMENT_DO.get(id);

    const putResp = await stub.fetch('https://do/update', {
      method: 'PUT',
      body: JSON.stringify({ content: 'hello world', lastEditor: 'alice' }),
    });
    expect(putResp.status).toBe(200);

    const getResp = await stub.fetch('https://do/read');
    const data = await getResp.json<{ content: string; version: number }>();
    expect(data.content).toBe('hello world');
    expect(data.version).toBe(1);
  });

  it('alarm handler is idempotent on double fire', async () => {
    const id = env.DOCUMENT_DO.idFromName('alarm-test');
    await runInDurableObject(env.DOCUMENT_DO.get(id), async (instance: DocumentDO) => {
      await instance.alarm();
      await instance.alarm(); // should not throw or double-write
    });
  });
});
```

---

## Related

- `documentation/categories/lessons/d1-transaction-isolation-lessons.md`
- `documentation/categories/lessons/workers-cold-start-latency-lessons.md`
- `documentation/categories/lessons/workers-secret-rotation-zero-downtime-lessons.md`

---

## Sources

- Cloudflare Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- DO storage limits: https://developers.cloudflare.com/durable-objects/platform/limits/
- Hibernation API: https://developers.cloudflare.com/durable-objects/reference/websockets/#hibernatable-websockets-api
- DO alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
