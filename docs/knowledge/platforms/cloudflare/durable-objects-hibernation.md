# durable-objects-hibernation

**Issue:** Using Durable Object hibernation to reduce costs during idle periods
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without hibernation, a Durable Object isolate stays alive (and billing) even when waiting for the next request. Hibernation allows the DO runtime to evict idle objects and restore them when new requests arrive, reducing duration costs significantly.

## Pattern / Solution

```typescript
import { DurableObject } from 'cloudflare:workers';

export class ChatRoom extends DurableObject {
  private messages: string[] = [];

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    // Restore state from storage (called on every cold start)
    this.ctx.blockConcurrencyWhile(async () => {
      this.messages = (await this.ctx.storage.get<string[]>('messages')) ?? [];
    });
  }

  async fetch(request: Request): Promise<Response> {
    // Handle HTTP requests to the DO
    const url = new URL(request.url);

    if (url.pathname === '/messages') {
      return Response.json(this.messages);
    }

    if (url.pathname === '/post' && request.method === 'POST') {
      const { text } = await request.json() as { text: string };
      this.messages.push(text);
      // Persist state so it survives hibernation
      await this.ctx.storage.put('messages', this.messages);
      return Response.json({ ok: true });
    }

    return new Response('Not Found', { status: 404 });
  }
}
```

```toml
# wrangler.toml — hibernation is opt-in per DO class
[[durable_objects.bindings]]
name = "CHAT_ROOM"
class_name = "ChatRoom"

[durable_objects]
# Hibernation is enabled automatically when using the DurableObject base class
# from 'cloudflare:workers' — no extra config needed
```

**Key design principles for hibernation:**
1. **Always persist state** before returning from `fetch()` or `alarm()`.
2. **Restore state** in the constructor using `ctx.blockConcurrencyWhile()`.
3. **Do not store state in module-level variables** — they are lost on hibernation.
4. Use `ctx.storage` as the source of truth.

**Checking if the DO was hibernated:**
```typescript
// In constructor, check if storage has data — indicates a restore from hibernation
const isRestore = await this.ctx.storage.get('initialized');
if (!isRestore) {
  await this.ctx.storage.put('initialized', true);
  // First-time initialization
}
```

## Gotchas
- The DO runtime decides **when** to hibernate — you cannot force or prevent it.
- Hibernation evicts the JavaScript heap; in-memory data (class properties not in `ctx.storage`) is **lost**.
- `ctx.blockConcurrencyWhile()` in the constructor ensures state is loaded before any requests are processed.
- Objects with open WebSocket connections use **WebSocket Hibernation** — a separate API (see `durable-objects-websocket-hibernation.md`).
- DO alarms are preserved across hibernation — the alarm fires even if the DO was evicted.
- Storage reads in the constructor add cold-start latency; cache aggressively in memory after loading.

## Related
- `durable-objects-websocket-hibernation.md`
- `durable-objects-alarms.md`
- `durable-objects-patterns.md`
- `durable-objects-best-practices.md`
