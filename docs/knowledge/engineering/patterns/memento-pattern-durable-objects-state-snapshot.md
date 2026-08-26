# Memento Pattern: Durable Objects State Snapshot

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Durable Object accumulates complex in-memory state — a collaborative post editor, an anonymous poll, a moderation queue — and needs the ability to undo the last N operations, roll back to a known-good checkpoint after a failed batch mutation, or fork state for preview without committing. Storing each mutation as a raw diff is error-prone; rebuilding state from scratch by replaying the event log is too slow for interactive undo within a single WebSocket session.

## Context

Durable Objects provide a private, consistent key-value storage (`this.ctx.storage`) attached to a single JS instance. All reads and writes within a transaction are serialised. Because the DO owns its state entirely, it can implement the Memento pattern by serialising its current state into a snapshot value and persisting it under a versioned key. The originator (the DO itself) creates and restores mementos; the caretaker (the client or a controller method) holds the stack of snapshot IDs and requests rollback without understanding the internal state shape.

## Defining the Memento and Originator

The DO state is the "originator". A memento is a plain serialisable object capturing the full state at one point in time.

```typescript
// src/durable-objects/post-editor-do.ts
import type { DurableObjectState } from '@cloudflare/workers-types';

// Internal state shape — private to the DO
interface EditorState {
  title: string;
  body: string;
  tags: string[];
  updatedAt: string;
}

// Memento — opaque to callers; only the DO knows how to restore it
interface EditorMemento {
  snapshotId: string;
  capturedAt: string;
  state: EditorState;
}

export class PostEditorDO {
  private state: DurableObjectState;
  private current: EditorState = { title: '', body: '', tags: [], updatedAt: '' };

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async initialize(): Promise<void> {
    const saved = await this.state.storage.get<EditorState>('current');
    if (saved) this.current = saved;
  }
}
```

## Creating Snapshots (Save Memento)

`saveSnapshot` serialises current state under a versioned key and pushes the ID onto a caretaker stack also stored in DO storage.

```typescript
// inside PostEditorDO

  private async saveSnapshot(label?: string): Promise<string> {
    const snapshotId = `snap:${Date.now()}:${crypto.randomUUID().slice(0, 8)}`;
    const memento: EditorMemento = {
      snapshotId,
      capturedAt: new Date().toISOString(),
      state: structuredClone(this.current),
    };

    // Persist memento alongside the current state in one transaction
    await this.state.storage.transaction(async (txn) => {
      await txn.put(snapshotId, memento);

      // Maintain caretaker stack (max 20 snapshots)
      const stack = (await txn.get<string[]>('snapshot_stack')) ?? [];
      stack.push(snapshotId);
      if (stack.length > 20) {
        const evicted = stack.shift()!;
        await txn.delete(evicted);
      }
      await txn.put('snapshot_stack', stack);
    });

    return snapshotId;
  }
```

## Restoring from a Snapshot (Restore Memento)

`restoreSnapshot` reads the memento back, replaces in-memory state, and persists the restored state as the new current — without removing the snapshot itself (enabling multi-level undo).

```typescript
// inside PostEditorDO

  private async restoreSnapshot(snapshotId: string): Promise<void> {
    const memento = await this.state.storage.get<EditorMemento>(snapshotId);
    if (!memento) {
      throw new Error(`Snapshot not found: ${snapshotId}`);
    }

    this.current = structuredClone(memento.state);

    await this.state.storage.transaction(async (txn) => {
      await txn.put('current', this.current);
      // Record the restore in a separate audit trail
      await txn.put(`restore:${Date.now()}`, { snapshotId, restoredAt: new Date().toISOString() });
    });
  }
```

## Exposing Snapshot Operations via fetch()

The DO's `fetch` handler routes snapshot commands, keeping the Memento implementation entirely inside the DO boundary.

```typescript
// inside PostEditorDO — full fetch handler

  async fetch(req: Request): Promise<Response> {
    await this.initialize();
    const url = new URL(req.url);

    // Apply an edit and auto-snapshot the previous state
    if (req.method === 'PATCH' && url.pathname === '/edit') {
      const patch = await req.json<Partial<EditorState>>();
      await this.saveSnapshot(); // caretaker calls this before mutation
      Object.assign(this.current, patch, { updatedAt: new Date().toISOString() });
      await this.state.storage.put('current', this.current);
      return Response.json({ ok: true, state: this.current });
    }

    // List available snapshots (caretaker view)
    if (req.method === 'GET' && url.pathname === '/snapshots') {
      const stack = (await this.state.storage.get<string[]>('snapshot_stack')) ?? [];
      const mementos = await Promise.all(
        stack.map(id => this.state.storage.get<EditorMemento>(id))
      );
      return Response.json(
        mementos
          .filter(Boolean)
          .map(m => ({ snapshotId: m!.snapshotId, capturedAt: m!.capturedAt }))
          .reverse()  // most recent first
      );
    }

    // Restore a snapshot by ID
    if (req.method === 'POST' && url.pathname === '/restore') {
      const { snapshotId } = await req.json<{ snapshotId: string }>();
      await this.restoreSnapshot(snapshotId);
      return Response.json({ ok: true, restoredState: this.current });
    }

    // Undo — restore the most recent snapshot
    if (req.method === 'POST' && url.pathname === '/undo') {
      const stack = (await this.state.storage.get<string[]>('snapshot_stack')) ?? [];
      const last = stack.at(-1);
      if (!last) return Response.json({ error: 'no_snapshots' }, { status: 409 });
      await this.restoreSnapshot(last);
      return Response.json({ ok: true, restoredState: this.current, snapshotId: last });
    }

    // Get current state
    if (req.method === 'GET' && url.pathname === '/state') {
      return Response.json(this.current);
    }

    return new Response('Not Found', { status: 404 });
  }
```

## Worker Proxy — Routing Requests to the DO

```typescript
// src/index.ts
import type { Env } from './env';

export { PostEditorDO } from './durable-objects/post-editor-do';

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const postId = url.searchParams.get('postId');
    if (!postId) return new Response('Missing postId', { status: 400 });

    const id = env.POST_EDITOR.idFromName(postId);
    const stub = env.POST_EDITOR.get(id);
    return stub.fetch(req);
  },
};
```

## Anti-patterns

- Storing the snapshot stack in the Worker KV instead of DO storage — risks race conditions and loses the transactional guarantee
- Capturing snapshots after the mutation instead of before — undo restores the already-mutated state, not the prior one
- Deep-cloning large binary fields (e.g., base64 images) inside the memento — store only the delta or an R2 object key instead
- Unbounded snapshot stacks — evict old snapshots on every save; set a hard cap and a TTL-based cleanup alarm
- Exposing the raw `EditorState` interface as the public API — callers then couple to internal state shape; use the `snapshotId` handle only

## Gotchas

- `this.state.storage.transaction` in Durable Objects is synchronous-if-fast; avoid large `await` chains inside it that could cause contention
- DO hibernation evicts `this.current` from memory; always re-hydrate from storage at the top of `fetch` before reading in-memory fields
- `structuredClone` is available in Workers runtime since 2023; use it instead of `JSON.parse(JSON.stringify(...))` for correctness with typed arrays
- Storage limits: each DO has 128 KB per value; large state must be chunked or offloaded to R2, storing only a reference in the memento
- Snapshot IDs based on `Date.now()` can collide under rapid concurrent requests; append a UUID suffix as shown above

## Verification

```bash
# 1. Create initial state
curl -X PATCH 'https://example.com/editor?postId=p1' \
  -d '{"title":"Hello","body":"World"}' | jq .state

# 2. Make another edit
curl -X PATCH 'https://example.com/editor?postId=p1' \
  -d '{"body":"Updated body"}' | jq .state

# 3. List snapshots — expect at least one
curl 'https://example.com/editor/snapshots?postId=p1' | jq '.[0].snapshotId'

# 4. Undo — should restore "World" as body
curl -X POST 'https://example.com/editor/undo?postId=p1' | jq .restoredState.body

# 5. Confirm restored
curl 'https://example.com/editor/state?postId=p1' | jq .body
# Expected: "World"
```

## Related

- `documentation/docs/policies/patterns/snapshot-durable-objects-versioning.md`
- `documentation/docs/policies/patterns/distributed-lock-durable-objects.md`
- `documentation/docs/policies/patterns/event-sourcing-cloudflare-workers-d1.md`
- `documentation/docs/policies/patterns/per-tenant-durable-object.md`
- `documentation/docs/policies/patterns/unit-of-work-pattern-d1-workers.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/
- https://developers.cloudflare.com/durable-objects/reference/hibernatable-websockets-api/
- https://refactoring.guru/design-patterns/memento
- https://developers.cloudflare.com/durable-objects/best-practices/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
