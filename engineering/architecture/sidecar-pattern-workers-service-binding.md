# Sidecar Pattern Using Workers Service Bindings

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your business Worker accumulates cross-cutting concerns — authentication checks, structured logging, rate-limiting — mixed into every handler. Factoring them into a shared library couples all teams to the same release cycle and means a bug in the auth library requires redeploying every Worker that imports it.

---

## Context

The sidecar pattern from service-mesh architecture translates naturally to Cloudflare Workers via service bindings: a dedicated sidecar Worker sits alongside the main business Worker and handles cross-cutting concerns in isolation. The business Worker calls `env.SIDECAR.fetch()` for each inbound request; the sidecar validates the JWT, applies rate-limiting against a Durable Object counter, emits a structured log entry to a Queue, then either forwards the request to the business handler or rejects it with an appropriate HTTP error. Because the sidecar is a separate Worker deployment, it is versioned and deployed independently; the business Worker does not need to change when auth logic evolves. Service bindings are direct in-process calls within the same Cloudflare PoP — there is no HTTP overhead, no public DNS round-trip, and no TLS handshake, making the sidecar effectively free compared with a traditional proxy.

---

## Config — wrangler.toml (sidecar Worker)

```toml
# wrangler.toml for the sidecar
name = "sidecar-worker"
main = "src/sidecar.ts"
compatibility_date = "2025-09-01"

[vars]
JWT_ISSUER = "https://auth.example.com"
RATE_LIMIT_RPM = "60" # requests per minute per user

[[kv_namespaces]]
binding = "JWKS_CACHE"
id = "<kv-namespace-id>"

[durable_objects]
bindings = [
  { name = "RATE_LIMITER", class_name = "SlidingWindowLimiter" }
]

[[migrations]]
tag = "v1"
new_classes = ["SlidingWindowLimiter"]

[[queues.producers]]
queue = "audit-log"
binding = "AUDIT_QUEUE"
```

```toml
# wrangler.toml for the business Worker
name = "business-worker"
main = "src/business.ts"
compatibility_date = "2025-09-01"

[[services]]
binding = "SIDECAR"
service = "sidecar-worker"

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "<d1-database-id>"
```

---

## Implementation — sidecar Worker

```typescript
// src/sidecar.ts
import { SlidingWindowLimiter } from "./rate-limiter";

export { SlidingWindowLimiter };

export interface Env {
  JWT_ISSUER: string;
  RATE_LIMIT_RPM: string;
  JWKS_CACHE: KVNamespace;
  RATE_LIMITER: DurableObjectNamespace;
  AUDIT_QUEUE: Queue<AuditEntry>;
}

interface AuditEntry {
  requestId: string;
  userId: string;
  method: string;
  path: string;
  status: number;
  durationMs: number;
  timestamp: number;
}

interface JwtPayload {
  sub: string;
  exp: number;
  iss: string;
}

/** Minimal JWT verification using the Web Crypto API. */
async function verifyJwt(
  token: string,
  issuer: string,
  jwksCache: KVNamespace
): Promise<JwtPayload> {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("Malformed JWT");

  const [headerB64, payloadB64, signatureB64] = parts;
  const payload = JSON.parse(
    atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/"))
  ) as JwtPayload;

  if (payload.iss !== issuer) throw new Error("Invalid issuer");
  if (payload.exp * 1000 < Date.now()) throw new Error("Token expired");

  // In production: fetch JWKS from the KV cache and verify the RS256 signature.
  // Omitted for brevity — use a library such as `jose` compiled to a single file.

  return payload;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const start = Date.now();
    const url = new URL(request.url);
    const requestId = request.headers.get("X-Request-Id") ?? crypto.randomUUID();

    // ── 1. Authentication ────────────────────────────────────────────
    const authHeader = request.headers.get("Authorization") ?? "";
    if (!authHeader.startsWith("Bearer ")) {
      return new Response(JSON.stringify({ error: "Missing bearer token" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }

    let jwtPayload: JwtPayload;
    try {
      jwtPayload = await verifyJwt(
        authHeader.slice(7),
        env.JWT_ISSUER,
        env.JWKS_CACHE
      );
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "Invalid token", detail: (err as Error).message }),
        { status: 401, headers: { "Content-Type": "application/json" } }
      );
    }

    const userId = jwtPayload.sub;

    // ── 2. Rate limiting (sliding window via Durable Object) ─────────
    const limiterId = env.RATE_LIMITER.idFromName(userId);
    const limiter = env.RATE_LIMITER.get(limiterId);
    const rpmLimit = parseInt(env.RATE_LIMIT_RPM, 10);

    const limitRes = await limiter.fetch(
      new Request("https://do/check", {
        method: "POST",
        body: JSON.stringify({ userId, limitRpm: rpmLimit }),
        headers: { "Content-Type": "application/json" },
      })
    );

    if (limitRes.status === 429) {
      const retryAfter = limitRes.headers.get("Retry-After") ?? "60";
      return new Response(
        JSON.stringify({ error: "Rate limit exceeded" }),
        {
          status: 429,
          headers: {
            "Content-Type": "application/json",
            "Retry-After": retryAfter,
          },
        }
      );
    }

    // ── 3. Forward enriched request to the underlying handler ────────
    // The sidecar Worker does not have a reference to the business Worker;
    // the business Worker calls the sidecar and then handles business logic
    // itself. Here the sidecar returns a 200 with enriched headers and
    // the business Worker checks for the X-Sidecar-Ok sentinel.
    const responseStatus = 200;
    const durationMs = Date.now() - start;

    // ── 4. Emit audit log entry asynchronously ───────────────────────
    await env.AUDIT_QUEUE.send({
      requestId,
      userId,
      method: request.method,
      path: url.pathname,
      status: responseStatus,
      durationMs,
      timestamp: Date.now(),
    });

    // Return enriched context to the business Worker
    return new Response(null, {
      status: 200,
      headers: {
        "X-Sidecar-Ok": "1",
        "X-User-Id": userId,
        "X-Request-Id": requestId,
      },
    });
  },
};
```

---

## Rate-limiter Durable Object

```typescript
// src/rate-limiter.ts
import { DurableObject } from "cloudflare:workers";

interface CheckBody {
  userId: string;
  limitRpm: number;
}

export class SlidingWindowLimiter extends DurableObject {
  /**
   * Sliding-window rate limiter.
   * Stores a list of request timestamps in DO storage and evicts
   * entries older than 60 seconds on every check.
   */
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/check" || request.method !== "POST") {
      return new Response("Not found", { status: 404 });
    }

    const { limitRpm } = await request.json<CheckBody>();
    const now = Date.now();
    const windowMs = 60_000;

    const stored = await this.ctx.storage.get<number[]>("timestamps");
    const timestamps: number[] = (stored ?? []).filter(
      (t) => now - t < windowMs
    );

    if (timestamps.length >= limitRpm) {
      const oldest = timestamps[0];
      const retryAfterMs = windowMs - (now - oldest);
      const retryAfterSecs = Math.ceil(retryAfterMs / 1000);
      return new Response(null, {
        status: 429,
        headers: { "Retry-After": String(retryAfterSecs) },
      });
    }

    timestamps.push(now);
    await this.ctx.storage.put("timestamps", timestamps);

    return new Response(null, { status: 200 });
  }
}
```

---

## Business Worker — delegating to sidecar

```typescript
// src/business.ts

export interface Env {
  SIDECAR: Fetcher;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // ── Delegate cross-cutting concerns to the sidecar ───────────────
    const sidecarRes = await env.SIDECAR.fetch(request.clone());

    if (sidecarRes.status !== 200) {
      // Auth failure, rate-limit, etc. — pass through the sidecar response.
      return sidecarRes;
    }

    // The sidecar has verified auth and set enriched headers.
    const userId = sidecarRes.headers.get("X-User-Id") ?? "";
    const requestId = sidecarRes.headers.get("X-Request-Id") ?? "";

    // ── Business logic ───────────────────────────────────────────────
    const url = new URL(request.url);

    if (url.pathname === "/api/profile" && request.method === "GET") {
      const row = await env.DB
        .prepare(`SELECT id, name, email FROM users WHERE id = ?`)
        .bind(userId)
        .first<{ id: string; name: string; email: string }>();

      if (!row) return new Response("Not found", { status: 404 });

      return Response.json(
        { id: row.id, name: row.name, email: row.email },
        { headers: { "X-Request-Id": requestId } }
      );
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## Anti-patterns

- **Putting business logic in the sidecar** — the sidecar must remain a pure cross-cutting layer (auth, logging, rate-limiting); domain knowledge in the sidecar creates tight coupling and defeats the purpose of the pattern.
- **Calling `env.SIDECAR.fetch()` without cloning the request** — `Request` bodies are single-use streams; if the business Worker also needs to read the body, clone the request before passing it to the sidecar.
- **Forwarding the raw sidecar response to the browser** — the sidecar returns internal sentinel headers (`X-Sidecar-Ok`, `X-User-Id`); strip these before constructing the final response to the client.
- **Using a separate HTTP Worker as a sidecar** — a public-internet Worker-to-Worker call adds latency, egress cost, and a TLS handshake; always use service bindings (`Fetcher`) for in-network Worker-to-Worker communication.

---

## Gotchas

- Service bindings call the bound Worker's `fetch` handler directly; the bound Worker does **not** see `request.cf`, `request.headers.get("CF-Connecting-IP")`, or other Cloudflare-injected properties — pass them explicitly in headers if the sidecar needs them.
- Durable Object `idFromName(userId)` pins the rate-limiter instance to a single Cloudflare location; for globally distributed rate-limiting, consider a KV-based token bucket with lower precision.
- `request.clone()` consumes memory proportional to the request body size; for large file uploads, pass only the headers and metadata to the sidecar and let the business Worker stream the body.
- The sidecar and business Worker share the same CPU time budget per request on the calling isolate's side; a slow sidecar (e.g., a Durable Object with high storage latency) counts against the business Worker's 50 ms CPU limit.

---

## Verification

```bash
# Deploy the sidecar first
wrangler deploy --config wrangler-sidecar.toml

# Deploy the business Worker (references the sidecar by service name)
wrangler deploy --config wrangler-business.toml

# Test: valid JWT → 200 from business Worker
curl -si https://business-worker.example.workers.dev/api/profile \
  -H "Authorization: Bearer <valid-jwt>" \
  | grep -E 'HTTP|X-Request-Id'

# Test: missing token → 401 from sidecar (forwarded by business Worker)
curl -si https://business-worker.example.workers.dev/api/profile \
  | grep -E 'HTTP|error'

# Test: exhaust rate limit (61 rapid requests)
for i in $(seq 1 61); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    https://business-worker.example.workers.dev/api/profile \
    -H "Authorization: Bearer <valid-jwt>"
done
# Last few lines should show 429

# Confirm audit log entries landed in the queue consumer
wrangler queues list-messages audit-log
```

---

## Related

- `micro-frontends-workers-routing.md`
- `shared-nothing-workers-stateless-design.md`

---

## Sources

- Cloudflare Workers Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Sidecar Pattern (Azure Architecture Center) — https://learn.microsoft.com/en-us/azure/architecture/patterns/sidecar
