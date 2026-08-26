# Workers RPC and Service Binding Patterns — Typed Cross-Worker Calls

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You have split your application into multiple Workers (auth, API, image-processing, queuing)
and need them to call each other without going through HTTP — no external round-trips, no
TLS overhead, no ingress billing.  Or you have a Worker that needs to call a Durable Object
method directly instead of serializing a request over `fetch()`.  You want TypeScript types
on both sides of the call so a signature change in the callee is a compile-time error in
the caller.

## Context

**Service Bindings** let one Worker call another Worker's handler via an in-process
(zero-egress) route.  Before 2024, service bindings only supported `fetch()`-style calls
(HTTP semantics over an internal channel).  In 2024 Cloudflare shipped **Workers RPC**:
a typed, method-call interface built on the `WorkerEntrypoint` and `DurableObject`
base classes using the `RpcStub` pattern.

Key concepts:

- `WorkerEntrypoint` — a base class your Worker can extend to expose named RPC methods.
- `RpcStub` — a client-side proxy object; calling `stub.myMethod(args)` dispatches to the
  remote Worker's `myMethod` over the internal channel.
- `RpcTarget` — a base class for objects returned from RPC methods; allows chaining RPC
  calls without round-tripping back to the caller.
- **Structured clone** — arguments and return values are serialized via the structured clone
  algorithm (like `postMessage`); `Request`/`Response` objects, `ReadableStream`,
  `ArrayBuffer`, and basic JSON types are all supported.
- **No HTTP overhead** — RPC calls are routed internally; they do not count as external
  subrequests and do not appear in the Cloudflare Access or WAF layers.

Compatibility date `2024-04-03` or later required for `WorkerEntrypoint` and named
entrypoints.

## Section 1 — Basic Service Binding with RPC

### Callee Worker (the service)

```toml
# auth-service/wrangler.toml
name               = "auth-service"
main               = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "SESSIONS"
id      = "abc123..."
```

```typescript
// auth-service/src/index.ts
import { WorkerEntrypoint } from "cloudflare:workers";

interface Env {
  SESSIONS: KVNamespace;
}

// Export a named entrypoint class — callers bind to this class
export class AuthService extends WorkerEntrypoint<Env> {
  // Called by service binding callers via RPC
  async validateToken(token: string): Promise<{ userId: string; valid: boolean }> {
    if (!token || token.length < 16) {
      return { userId: "", valid: false };
    }

    const session = await this.env.SESSIONS.get<{ userId: string }>(token, "json");
    if (!session) {
      return { userId: "", valid: false };
    }

    return { userId: session.userId, valid: true };
  }

  async createSession(userId: string, ttlSeconds = 3600): Promise<string> {
    const token = crypto.randomUUID().replace(/-/g, "");
    await this.env.SESSIONS.put(
      token,
      JSON.stringify({ userId }),
      { expirationTtl: ttlSeconds }
    );
    return token;
  }

  async revokeSession(token: string): Promise<void> {
    await this.env.SESSIONS.delete(token);
  }

  // default fetch handler still needed for direct HTTP traffic or health checks
  async fetch(request: Request): Promise<Response> {
    return new Response("auth-service ok");
  }
}

export default {
  fetch: () => new Response("Use the AuthService entrypoint"),
};
```

### Caller Worker

```toml
# api-worker/wrangler.toml
name               = "api-worker"
main               = "src/index.ts"
compatibility_date = "2024-09-23"

[[services]]
binding     = "AUTH"
service     = "auth-service"
entrypoint  = "AuthService"    # must match the exported class name
```

```typescript
// api-worker/src/index.ts
// Import the remote class type for type-safety (source of truth stays in auth-service)
import type { AuthService } from "../../auth-service/src/index";

interface Env {
  AUTH: Service<AuthService>;   // typed stub
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/login" && request.method === "POST") {
      const { userId } = await request.json() as { userId: string };
      // RPC call — no HTTP, no JSON serialization for the transport layer
      const token = await env.AUTH.createSession(userId, 7200);
      return Response.json({ token });
    }

    // Validate the Bearer token on every other request
    const authHeader = request.headers.get("Authorization") ?? "";
    const token = authHeader.replace(/^Bearer\s+/, "");

    const { valid, userId } = await env.AUTH.validateToken(token);
    if (!valid) {
      return new Response("Unauthorized", { status: 401 });
    }

    // ... handle authenticated request
    return Response.json({ userId, path: url.pathname });
  },
};
```

## Section 2 — Returning RpcTarget Objects (Chaining)

An RPC method can return an object that itself has callable methods, avoiding a second
round-trip to identify a resource before operating on it.

```typescript
// image-service/src/index.ts
import { WorkerEntrypoint, RpcTarget } from "cloudflare:workers";

class ImageJob extends RpcTarget {
  private jobId: string;
  private env: Env;

  constructor(jobId: string, env: Env) {
    super();
    this.jobId = jobId;
    this.env = env;
  }

  async getStatus(): Promise<{ status: string; url?: string }> {
    const job = await this.env.DB.prepare(
      "SELECT status, output_url FROM jobs WHERE id = ?"
    ).bind(this.jobId).first<{ status: string; output_url?: string }>();

    return { status: job?.status ?? "not_found", url: job?.output_url };
  }

  async cancel(): Promise<void> {
    await this.env.DB.prepare(
      "UPDATE jobs SET status = 'cancelled' WHERE id = ? AND status = 'pending'"
    ).bind(this.jobId).run();
  }
}

interface Env {
  DB: D1Database;
}

export class ImageService extends WorkerEntrypoint<Env> {
  async submitJob(imageUrl: string, transforms: object): Promise<ImageJob> {
    const jobId = crypto.randomUUID();
    await this.env.DB.prepare(
      "INSERT INTO jobs (id, status, source_url, transforms) VALUES (?, 'pending', ?, ?)"
    ).bind(jobId, imageUrl, JSON.stringify(transforms)).run();

    // Return an RpcTarget — the caller can chain method calls on this object
    return new ImageJob(jobId, this.env);
  }

  async fetch(request: Request): Promise<Response> {
    return new Response("image-service ok");
  }
}
```

```typescript
// Caller side — chain without a second RPC for job lookup
import type { ImageService } from "../../image-service/src/index";

interface Env {
  IMG: Service<ImageService>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // submitJob returns an ImageJob stub — chaining works transparently
    const job = await env.IMG.submitJob(
      "https://example.com/photo.jpg",
      { width: 800, format: "webp" }
    );

    const { status } = await job.getStatus();
    return Response.json({ status });
  },
};
```

## Section 3 — Durable Object RPC

DOs expose the same RPC pattern.  Any public method on a `DurableObject` subclass is
callable from a service binding stub.

```typescript
// counter-do/src/index.ts
import { DurableObject } from "cloudflare:workers";

export class CounterDO extends DurableObject {
  private count = 0;

  async increment(by = 1): Promise<number> {
    this.count += by;
    await this.ctx.storage.put("count", this.count);
    return this.count;
  }

  async get(): Promise<number> {
    this.count = (await this.ctx.storage.get<number>("count")) ?? 0;
    return this.count;
  }

  async reset(): Promise<void> {
    this.count = 0;
    await this.ctx.storage.delete("count");
  }

  async fetch(request: Request): Promise<Response> {
    return Response.json({ count: await this.get() });
  }
}
```

```typescript
// Caller calling a DO method via RPC (no need to synthesize a Request)
import type { CounterDO } from "../../counter-do/src/index";

interface Env {
  COUNTER: DurableObjectNamespace<CounterDO>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const id = env.COUNTER.idFromName("global");
    const stub = env.COUNTER.get(id);

    // Direct method call instead of stub.fetch(new Request("/increment"))
    const newCount = await stub.increment(1);
    return Response.json({ count: newCount });
  },
};
```

## Section 4 — TypeScript Setup for Cross-Worker Types

To get type-safety in callers when the callee lives in a separate package:

### Option A: shared types package

```
packages/
  auth-types/
    src/
      index.ts     ← export interface IAuthService { validateToken(t: string): Promise<...> }
  auth-service/    ← implements IAuthService
  api-worker/      ← imports IAuthService, casts env.AUTH to Service<IAuthService>
```

### Option B: import the callee's class type directly

If the monorepo contains both Workers, import the class type file directly as shown in
Section 1.  The import is type-only (`import type`) — no runtime code from the callee is
bundled into the caller.

### tsconfig.json path alias

```json
{
  "compilerOptions": {
    "paths": {
      "auth-service/*": ["../../auth-service/src/*"]
    }
  }
}
```

## Mobile vs Desktop Considerations

- **RPC call latency is ~0–2 ms** on the same PoP; this adds negligible latency regardless
  of whether the end user is on mobile or desktop.  The end-user device type does not affect
  internal Worker-to-Worker routing.
- **Streaming responses from RPC** — `ReadableStream` can be returned from RPC methods and
  is transferred without buffering.  Mobile clients that receive streaming responses benefit
  from lower time-to-first-byte even through a multi-Worker pipeline.
- **Device type propagation** — `request.cf.deviceType` is only available in the outermost
  Worker that receives the original request.  If you need device type inside a callee
  Worker, pass it as an explicit RPC argument:

```typescript
// caller
const result = await env.AUTH.validateToken(token, request.cf?.deviceType ?? "desktop");

// callee
async validateToken(token: string, deviceType: string): Promise<...> { ... }
```

## Anti-patterns

- **Using `fetch()`-based service bindings for structured data** — before RPC, you had to
  serialize to JSON, create a `Request`, and parse the `Response`.  Replace these with
  typed RPC methods to remove boilerplate and gain type safety.
- **Returning non-cloneable values from RPC methods** — functions, `Promise` instances
  (except via `RpcTarget`), and browser-only APIs are not structured-cloneable and will
  throw at runtime.  Return plain objects, typed `RpcTarget` instances, or transferable
  types.
- **Calling RPC methods in a tight loop without batching** — each RPC call has a small
  overhead even on the internal channel.  If you need to call `increment()` 500 times,
  add a `batchIncrement(n: number)` method instead.
- **Exposing secrets via RPC return values** — RPC methods are still subject to your own
  authorization logic.  A misconfigured binding lets any Worker in your account call any
  method; validate that the call is from an authorized caller if the method is sensitive.

## Gotchas

- **Named entrypoints require `compatibility_date = "2024-04-03"` or later** — older
  compatibility dates fall back to the default `fetch` handler only.
- **`this.env` is available in `WorkerEntrypoint` but NOT in plain class methods** — you
  must use the entrypoint class pattern; a plain exported function cannot access `this.env`.
- **RPC stubs are not serializable** — you cannot store an `env.AUTH` stub in KV or pass
  it through a Queue message.  Stubs are live only within the current request lifecycle.
- **Circular service bindings** — Worker A binding to B, B binding back to A is supported
  but creates a dependency cycle that can be hard to debug.  Prefer a DAG (directed acyclic
  graph) of Worker dependencies.
- **`RpcTarget` objects have a limited lifetime** — an `RpcTarget` returned from an RPC
  method is tied to the original request context.  Holding a reference to it after the
  request completes is not valid.
- **`wrangler dev` hot reload and service bindings** — in local development with `wrangler
  dev`, service bindings are resolved by launching the bound Worker as a local process.
  If the callee Worker is not running, the binding returns a connection error.  Use
  `wrangler dev --service auth-service=./auth-service` or run all Workers in the same
  `wrangler dev` session via a `wrangler.toml` with all services declared.

## Verification

```bash
# 1. Confirm service bindings are wired in wrangler.toml
npx wrangler deploy --dry-run --outdir ./out api-worker/wrangler.toml
cat ./out/api-worker.json | jq '.services'

# 2. Local dev with a bound service
npx wrangler dev --config api-worker/wrangler.toml \
  --service AUTH=auth-service/wrangler.toml

# 3. Integration test — call an RPC method end-to-end
curl -X POST http://localhost:8787/login \
  -H "Content-Type: application/json" \
  -d '{"userId": "user-123"}'
# Expect: {"token": "<uuid>"}

# 4. Verify no external subrequests (RPC should not appear in subrequest logs)
npx wrangler tail api-worker --format=pretty | grep subrequest

# 5. TypeScript compile check
npx tsc --noEmit -p api-worker/tsconfig.json
```

## Related

- `workers-service-bindings-advanced.md` — fetch()-style service bindings
- `workers-rpc.md` — foundational RPC concepts
- `durable-objects-best-practices.md` — DO lifecycle and sharding
- `durable-objects-real-time-state.md` — stateful DO patterns
- `workers-module-workers.md` — ES module Worker format required for RPC
- `workers-types-migration.md` — updating `@cloudflare/workers-types` for new APIs

## Sources

- Workers RPC overview: https://developers.cloudflare.com/workers/runtime-apis/rpc/
- WorkerEntrypoint: https://developers.cloudflare.com/workers/runtime-apis/rpc/lifecycle/
- RpcTarget: https://developers.cloudflare.com/workers/runtime-apis/rpc/compatible-types/
- Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Durable Objects RPC: https://developers.cloudflare.com/durable-objects/api/base-class/#rpc-methods
- Named entrypoints: https://developers.cloudflare.com/workers/runtime-apis/handlers/named-entrypoints/
