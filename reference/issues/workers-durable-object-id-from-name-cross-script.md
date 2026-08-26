# Durable Object ID Collision: idFromName() Generates Different IDs Across Scripts

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Two Cloudflare Workers that are supposed to share the same Durable Object instance (by name) are silently accessing different instances. No error is thrown — both calls succeed — but mutations made by Worker A are invisible to Worker B, and vice versa.

```
# Worker A writes a counter: { count: 42 }
# Worker B reads the "same" DO by name: { count: 0 }

# Or: two Workers coordinating on a chat room by room ID
# send messages to different DOs, appearing to talk past each other
```

This is one of the most insidious Durable Object bugs: it fails silently.

---

## Context

- **Runtime**: Cloudflare Workers
- **Feature**: Durable Objects (`idFromName()` method)
- **Pattern**: Cross-script DO coordination, shared state between multiple Workers
- **Wrangler**: 3.x
- **TypeScript**: 5.x with `@cloudflare/workers-types`

---

## Root Cause

`DurableObjectNamespace.idFromName(name: string)` derives a deterministic 256-bit ID from the combination of:

1. The **name string** you provide.
2. The **unique identifier of the Durable Object class** — which is scoped to the **script (Worker)** that owns the class.

When the same DO class is referenced via different `script_name` bindings in `wrangler.toml`, or when two Workers each define their own DO class with the same class name, `idFromName("room-1")` produces **different IDs** in each Worker, even though the name string is identical.

From the Cloudflare docs:
> "The ID is derived from the object's name and the script and class name of the Durable Object class."

This means DO IDs are **not portable across scripts**. Only the Worker that owns the class (defined as the script where the DO class implementation lives) generates canonical IDs. Any binding that uses `script_name` to point at another Worker's DO class will, if it also calls `idFromName()`, generate a different hash namespace.

**Hash formula (conceptual)**:
```
id = hash(script_unique_id + ":" + class_name + ":" + name_string)
```

The `script_unique_id` differs between Workers, so the same `class_name + name_string` yields different IDs.

---

## Broken Code

```toml
# worker-a/wrangler.toml — Worker A defines and owns the DO class
name = "worker-a"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[durable_objects]
bindings = [
  { name = "COUNTER", class_name = "Counter" }
]

[[migrations]]
tag = "v1"
new_classes = ["Counter"]
```

```toml
# worker-b/wrangler.toml — Worker B tries to share the same DO
name = "worker-b"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[durable_objects]
bindings = [
  # WRONG: re-declaring same class_name without script_name,
  # OR using script_name but still calling idFromName() here
  { name = "COUNTER", class_name = "Counter", script_name = "worker-a" }
]
```

```typescript
// worker-a/src/index.ts
export class Counter implements DurableObject {
  private count = 0;

  constructor(private state: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    this.count++;
    await this.state.storage.put('count', this.count);
    return Response.json({ count: this.count });
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Worker A generates an ID from "global-counter"
    const id = env.COUNTER.idFromName('global-counter');
    const stub = env.COUNTER.get(id);
    return stub.fetch(request);
  },
};

interface Env {
  COUNTER: DurableObjectNamespace;
}
```

```typescript
// worker-b/src/index.ts — BROKEN
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Worker B calls idFromName() on a binding that uses script_name="worker-a"
    // This generates a DIFFERENT ID hash than Worker A's idFromName()
    // because the hash includes worker-b's script unique identifier
    const id = env.COUNTER.idFromName('global-counter'); // WRONG ID
    const stub = env.COUNTER.get(id);
    return stub.fetch(request); // Reaches a DIFFERENT DO instance
  },
};

interface Env {
  COUNTER: DurableObjectNamespace;
}
```

---

## Fix

### Option 1 — Always call idFromName() from the owning script (preferred)

Only Worker A (the script that defines `Counter`) should call `idFromName()`. Worker B should receive the serialized ID string and reconstruct it with `idFromString()`.

```typescript
// worker-a/src/index.ts — FIXED: expose ID via API
export class Counter implements DurableObject {
  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/increment') {
      const count = ((await this.state.storage.get<number>('count')) ?? 0) + 1;
      await this.state.storage.put('count', count);
      return Response.json({ count });
    }
    const count = (await this.state.storage.get<number>('count')) ?? 0;
    return Response.json({ count });
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/counter-id') {
      // Return the canonical ID string so other Workers can use idFromString()
      const id = env.COUNTER.idFromName('global-counter');
      return Response.json({ id: id.toString() });
    }

    const id = env.COUNTER.idFromName('global-counter');
    const stub = env.COUNTER.get(id);
    return stub.fetch(new Request('https://do/increment'));
  },
};

interface Env {
  COUNTER: DurableObjectNamespace;
}
```

```typescript
// worker-b/src/index.ts — FIXED: fetch ID from worker-a, use idFromString()
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Get the canonical DO ID from the owning Worker
    const idRes = await fetch('https://worker-a.example.com/counter-id');
    const { id: idString } = await idRes.json<{ id: string }>();

    // Reconstruct the ID — idFromString() does NOT hash, just parses
    const id = env.COUNTER.idFromString(idString);
    const stub = env.COUNTER.get(id);

    return stub.fetch(new Request('https://do/increment'));
  },
};

interface Env {
  COUNTER: DurableObjectNamespace;
}
```

### Option 2 — Consolidate DO access into a single Worker (simplest)

If coordination is the goal, make only one Worker interact with the DO and expose an HTTP API. Worker B calls Worker A's API rather than the DO directly.

```typescript
// worker-b/src/index.ts — FIXED: delegate to worker-a's API
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // All DO access goes through worker-a — no DO binding needed in worker-b
    const response = await fetch('https://worker-a.example.com/increment', {
      method: 'POST',
    });
    return response;
  },
};

interface Env {} // No COUNTER binding needed
```

### Option 3 — Use a Service Binding instead of direct DO binding

```toml
# worker-b/wrangler.toml — FIXED: use service binding to worker-a
name = "worker-b"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[services]]
binding = "WORKER_A"
service = "worker-a"
# No [durable_objects] binding for COUNTER here
```

```typescript
// worker-b/src/index.ts — FIXED: service binding proxies through worker-a
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Calls worker-a's fetch handler — DO access happens inside worker-a
    return env.WORKER_A.fetch(new Request('https://internal/increment'));
  },
};

interface Env {
  WORKER_A: Fetcher;
}
```

---

## Verification

```bash
# 1. Deploy both workers
npx wrangler deploy --config worker-a/wrangler.toml
npx wrangler deploy --config worker-b/wrangler.toml

# 2. Increment via Worker A
curl -X POST https://worker-a.example.com/increment
# => {"count": 1}

# 3. Read via Worker B — should see count=1 if fix is correct
curl https://worker-b.example.com/count
# => {"count": 1}  (broken: {"count": 0})

# 4. Increment several more times via A, verify B sees same value
for i in {1..5}; do curl -X POST https://worker-a.example.com/increment; done
curl https://worker-b.example.com/count
# => {"count": 6}

# 5. Inspect DO ID logged by each worker
npx wrangler tail worker-a --format=pretty | grep 'DO id'
npx wrangler tail worker-b --format=pretty | grep 'DO id'
# Both should print the same 64-char hex string
```

---

## Anti-patterns

- Calling `idFromName()` from multiple scripts with a `script_name` cross-binding and expecting the same ID.
- Assuming DO IDs are purely derived from the name string — they are script-scoped.
- Using the same DO class name in two different Workers and expecting them to share instances.
- Storing a DO ID in KV as a string from one Worker and generating it via `idFromName()` in another — they will not match.

---

## Gotchas

- `idFromString()` accepts the 64-character hex string returned by `id.toString()` — it does **not** re-hash.
- A DO ID generated by `idFromName()` is deterministic within a single script's namespace forever; you can cache it safely.
- When using `script_name` in a DO binding, the DO runs in the named script's isolate — but `idFromName()` called in the *binding* script still hashes using the *binding* script's unique ID.
- Durable Object migration (`new_classes`, `renamed_classes`) changes the unique class tag, which changes `idFromName()` results — plan migrations carefully.
- In local `wrangler dev`, cross-script DO bindings may behave differently than in production; always validate on deployed Workers.

---

## Related

- `documentation/categories/issues/workers-fetch-null-body-consumed-error.md`
- `documentation/categories/issues/workers-kv-binding-undefined-wrangler-toml.md`
- `documentation/categories/issues/d1-wrangler-local-remote-binding-mismatch.md`

---

## Sources

- https://developers.cloudflare.com/durable-objects/api/id-management/
- https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-from-a-worker/
- https://developers.cloudflare.com/workers/wrangler/configuration/#durable-objects
- https://developers.cloudflare.com/durable-objects/reference/in-memory-state/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
