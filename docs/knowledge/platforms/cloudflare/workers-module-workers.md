# workers-module-workers

**Issue:** Differences between Service Worker format and ES Module format Workers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare Workers support two syntaxes: the legacy Service Worker format (using `addEventListener`) and the modern ES Module format (using `export default`). The module format is required for Durable Objects, Queues, Email, and most new features.

## Pattern / Solution

```typescript
// ❌ Legacy Service Worker format (avoid for new projects)
addEventListener('fetch', (event) => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  return new Response('Hello');
}
```

```typescript
// ✅ ES Module format — required for all modern Workers features
export interface Env {
  KV: KVNamespace;
  DB: D1Database;
  DO: DurableObjectNamespace;
  MY_QUEUE: Queue;
}

export default {
  // HTTP requests
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    ctx.waitUntil(trackRequest(request, env));
    return new Response('Hello from module worker');
  },

  // Cron triggers
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runJob(env));
  },

  // Queue consumer
  async queue(batch: MessageBatch, env: Env, ctx: ExecutionContext): Promise<void> {
    for (const msg of batch.messages) {
      await processMessage(msg.body, env);
      msg.ack();
    }
  },

  // Email handler
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext): Promise<void> {
    await message.forward('team@example.com');
  },

  // Tail worker handler
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    for (const e of events) console.log(e.outcome);
  },
};
```

```toml
# wrangler.toml — must declare module format
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-01-01"
# No "type = 'javascript'" needed — wrangler infers ESM from export default
```

## Gotchas
- In module Workers, `env` is passed as a **parameter** — there are no global bindings. Never use `self.KV` or similar.
- `ExecutionContext.waitUntil()` keeps the isolate alive after the response is sent; without it, async work after `return` is killed.
- `ExecutionContext.passThroughOnException()` makes the Worker fall back to the origin on unhandled errors.
- Durable Object classes **must** be exported as named exports in the same module or a separate file.
- The legacy format uses `event.waitUntil()` on the `FetchEvent`; the module format uses `ctx.waitUntil()`.
- Mixing formats in the same Worker is not supported.

## Related
- `workers-best-practices.md`
- `workers-service-bindings-advanced.md`
- `durable-objects-patterns.md`
- `wrangler-toml-reference.md`
