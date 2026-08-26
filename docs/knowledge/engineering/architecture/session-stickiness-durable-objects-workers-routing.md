# Session Stickiness with Durable Objects and Workers Routing

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Stateful application sessions — shopping carts, multi-step checkouts, real-time collaborative documents — need requests from the same user to land on the same logical "server" to avoid redundant state hydration or split-brain reads. On a globally distributed, stateless Workers platform, achieving this without a central sticky-session cookie and load-balancer affinity requires a different approach.

## Context

Cloudflare Workers route each request independently with no affinity guarantees. Durable Objects are globally unique actors identified by a stable name or ID; every `get(id).fetch()` call is routed to the same single instance worldwide. This makes DOs the natural "sticky" shard for a user session. The pattern replaces traditional load-balancer session affinity by encoding the session's DO ID in the client cookie and routing all subsequent requests through that DO.

## Architecture

```
Client (cookie: session-id=<doId>)
         │
         ▼
Cloudflare Workers (edge)
   ├─ No cookie? → create new SessionDO, set-cookie
   └─ Cookie present → get DO by id → forward request
                              │
                         SessionDO (single instance, global)
                           ├─ in-memory session state
                           └─ D1 / KV persistence on mutation
```

## Session Durable Object

```typescript
// src/session-do.ts
import { DurableObject } from "cloudflare:workers";

interface Env {
  SESSIONS: DurableObjectNamespace;
  DB: D1Database;
}

interface SessionState {
  userId?: string;
  cart: CartItem[];
  createdAt: number;
  lastSeen: number;
}

interface CartItem {
  productId: string;
  quantity: number;
}

const SESSION_IDLE_TTL_MS = 30 * 60 * 1000; // 30 minutes

export class SessionDO extends DurableObject {
  private state: SessionState = {
    cart: [],
    createdAt: Date.now(),
    lastSeen: Date.now(),
  };
  private loaded = false;

  private async ensureLoaded(): Promise<void> {
    if (this.loaded) return;
    const stored = await this.ctx.storage.get<SessionState>("session");
    if (stored) this.state = stored;
    this.loaded = true;
  }

  private async persist(): Promise<void> {
    this.state.lastSeen = Date.now();
    await this.ctx.storage.put("session", this.state);

    // Schedule self-eviction alarm so idle DOs don't accumulate
    await this.ctx.storage.setAlarm(Date.now() + SESSION_IDLE_TTL_MS);
  }

  async alarm(): Promise<void> {
    // Session expired — purge storage
    await this.ctx.storage.deleteAll();
  }

  async fetch(request: Request): Promise<Response> {
    await this.ensureLoaded();

    const url = new URL(request.url);

    if (url.pathname === "/session/get") {
      return Response.json(this.state);
    }

    if (url.pathname === "/session/authenticate" && request.method === "POST") {
      const { userId } = (await request.json()) as { userId: string };
      this.state.userId = userId;
      await this.persist();
      return Response.json({ ok: true });
    }

    if (url.pathname === "/cart/add" && request.method === "POST") {
      const item = (await request.json()) as CartItem;
      const existing = this.state.cart.find(
        (c) => c.productId === item.productId
      );
      if (existing) {
        existing.quantity += item.quantity;
      } else {
        this.state.cart.push(item);
      }
      await this.persist();
      return Response.json({ cart: this.state.cart });
    }

    if (url.pathname === "/cart/remove" && request.method === "POST") {
      const { productId } = (await request.json()) as { productId: string };
      this.state.cart = this.state.cart.filter(
        (c) => c.productId !== productId
      );
      await this.persist();
      return Response.json({ cart: this.state.cart });
    }

    return new Response("Not Found", { status: 404 });
  }
}
```

## Worker: Session Routing Middleware

```typescript
// src/worker.ts
import { SessionDO } from "./session-do";

export { SessionDO };

interface Env {
  SESSIONS: DurableObjectNamespace;
}

const SESSION_COOKIE = "cf-session-id";
const SESSION_MAX_AGE = 60 * 60 * 24 * 7; // 7 days

function getSessionIdFromCookie(request: Request): string | null {
  const cookie = request.headers.get("Cookie") ?? "";
  const match = cookie.match(new RegExp(`${SESSION_COOKIE}=([^;]+)`));
  return match ? match[1] : null;
}

function makeSetCookieHeader(doId: string): string {
  return [
    `${SESSION_COOKIE}=${doId}`,
    `Max-Age=${SESSION_MAX_AGE}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    "Secure",
  ].join("; ");
}

async function routeToSession(
  request: Request,
  env: Env,
  doId: DurableObjectId
): Promise<Response> {
  const stub = env.SESSIONS.get(doId);
  // Rewrite URL to internal DO path
  const url = new URL(request.url);
  const doRequest = new Request(`https://session-do${url.pathname}`, {
    method: request.method,
    headers: request.headers,
    body: request.body,
  });
  return stub.fetch(doRequest);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only apply sticky routing to session-bearing paths
    if (!url.pathname.startsWith("/session") && !url.pathname.startsWith("/cart")) {
      return new Response("Not Found", { status: 404 });
    }

    let sessionId = getSessionIdFromCookie(request);
    let isNew = false;

    let doId: DurableObjectId;
    if (sessionId) {
      try {
        doId = env.SESSIONS.idFromString(sessionId);
      } catch {
        // Invalid or tampered cookie — start fresh
        doId = env.SESSIONS.newUniqueId();
        isNew = true;
      }
    } else {
      doId = env.SESSIONS.newUniqueId();
      isNew = true;
    }

    const response = await routeToSession(request, env, doId);

    // Attach or refresh session cookie on successful responses
    if (response.status < 500) {
      const mutableResponse = new Response(response.body, response);
      mutableResponse.headers.set(
        "Set-Cookie",
        makeSetCookieHeader(doId.toString())
      );
      if (isNew) {
        mutableResponse.headers.set("X-Session-Created", "1");
      }
      return mutableResponse;
    }

    return response;
  },
};
```

## Session Migration on Authentication

When an anonymous session upgrades to an authenticated user, the session ID may need to be rotated to prevent session-fixation attacks. Because the DO is its ID, rotation requires a copy operation:

```typescript
// In a /session/login handler in the Worker
async function rotateSession(
  oldDoId: DurableObjectId,
  userId: string,
  env: Env
): Promise<DurableObjectId> {
  // Read current anonymous session
  const oldStub = env.SESSIONS.get(oldDoId);
  const stateRes = await oldStub.fetch(
    new Request("https://session-do/session/get")
  );
  const oldState = await stateRes.json();

  // Create new authenticated session
  const newDoId = env.SESSIONS.newUniqueId();
  const newStub = env.SESSIONS.get(newDoId);

  // Authenticate and transfer cart
  await newStub.fetch(
    new Request("https://session-do/session/authenticate", {
      method: "POST",
      body: JSON.stringify({ userId }),
    })
  );

  for (const item of (oldState as any).cart ?? []) {
    await newStub.fetch(
      new Request("https://session-do/cart/add", {
        method: "POST",
        body: JSON.stringify(item),
      })
    );
  }

  // Invalidate old session
  await oldStub.fetch(
    new Request("https://session-do/session/invalidate", { method: "POST" })
  );

  return newDoId;
}
```

## Anti-patterns

- **Using user ID as the DO name** — a user with multiple concurrent browser tabs all hit the same single DO instance, which serializes all their requests; use a per-tab or per-device token instead.
- **Storing large blobs in DO storage** — DO storage has a 128 KB per-value limit; offload payloads to R2 and store only references in the session.
- **Never setting an alarm for eviction** — idle sessions accumulate DO instances indefinitely; always schedule an eviction alarm on last-write.
- **Trusting the cookie value as-is** — parse with `idFromString()` inside a try/catch; an invalid string panics otherwise.
- **Crossing sessions across subdomains without Secure + SameSite** — session cookies must be `HttpOnly; Secure; SameSite=Lax` to prevent CSRF and XSS theft.

## Gotchas

- `DurableObjectNamespace.idFromString()` expects the 64-hex-char string emitted by `doId.toString()`, not an arbitrary token; store the full DO ID string in the cookie, not a custom UUID.
- DO instances are routed to the colo nearest to their first-creation point, not the caller; a user travelling internationally may experience higher latency until migration occurs (which is automatic but not instant).
- The DO `fetch()` subrequest counts toward the 1000 subrequest limit per Worker invocation; sessions with many cart operations in one request can approach this limit.
- Alarm delivery is best-effort within ~30 s of the scheduled time; sessions may live slightly longer than `SESSION_IDLE_TTL_MS`.
- `newUniqueId()` generates a location hint from the current colo; pass `{ jurisdiction: "eu" }` if GDPR data-residency is required.

## Verification

1. `curl -c cookies.txt /cart/add -d '{"productId":"p1","quantity":1}'` — verify `Set-Cookie` header contains a 64-char hex ID.
2. Replay with `-b cookies.txt` — confirm the same DO instance responds (check `X-Session-Created` is absent).
3. Modify the cookie value to a random string — verify the Worker issues a new session instead of panicking.
4. Let the session idle past `SESSION_IDLE_TTL_MS` — verify DO alarm fires and storage is purged via `wrangler tail`.
5. Run a load test with 1000 concurrent sessions — confirm each session is routed to its own DO via unique DO IDs in logs.

## Related

- `workers-do-websocket-architecture.md`
- `multi-tenancy-isolation-patterns.md`
- `durable-objects-workflow-state-machine.md`
- `mediator-pattern-durable-objects-workers-coordination.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/id/
- https://developers.cloudflare.com/durable-objects/reference/alarms/
- https://owasp.org/www-community/attacks/Session_fixation
