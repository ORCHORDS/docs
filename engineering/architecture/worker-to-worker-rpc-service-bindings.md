# Worker-to-Worker RPC via Service Bindings — Zero-Latency Internal APIs

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A Cloudflare Workers application grows beyond a single Worker script into a suite of
specialized Workers: an auth Worker, a media-processing Worker, a notification Worker,
a billing Worker. These need to call each other. The naive approach — HTTP fetch between
Workers over the public internet — adds latency, incurs egress costs, exposes internal
APIs to the public network, and requires secret management for inter-service auth.
Cloudflare Service Bindings (also called Worker-to-Worker bindings) solve all four
problems: calls are routed in-process within Cloudflare's network at zero added latency,
never touch the public internet, do not count against egress, and do not require auth
tokens because the binding is an identity assertion.

With the Workers RPC (`WorkerEntrypoint`) API introduced in 2024, service bindings
escalate from plain HTTP proxying to fully typed RPC: the calling Worker invokes named
methods on the called Worker's exported class as if calling a local function.

Concrete use cases:
- Auth Worker validates JWT tokens called from API gateway Workers
- Notification Worker sends push/email called from business-logic Workers
- Media Worker runs FFmpeg WASM for chord-audio generation called from job Workers
- Billing Worker checks subscription limits called from feature-gate middleware

---

## Context

Two mechanisms exist for service-to-service communication in Workers:

| Mechanism | Protocol | Typed? | Cost |
|-----------|----------|--------|------|
| HTTP fetch via service binding | HTTP/1.1 or HTTP/2 | No (manual JSON) | Free, in-network |
| RPC via `WorkerEntrypoint` | Proprietary RPC | Yes (TypeScript) | Free, in-network |

Service bindings are declared in `wrangler.toml` and injected into the Worker's `Env`
object. The called Worker does not need a route or domain — it is only reachable via
bindings. This is the primary isolation mechanism for internal-only Workers.

Workers RPC serialises arguments using the structured clone algorithm, meaning you can
pass `ArrayBuffer`, `ReadableStream`, `Map`, `Date`, and plain objects without a manual
`JSON.stringify` / `JSON.parse` round-trip.

---

## Architecture

```
                     Cloudflare Edge (same PoP where possible)
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  API Gateway Worker                                         │
│   env.AUTH_WORKER.verifyToken(jwt)  ─────────────────────▶ Auth Worker  │
│   env.BILLING_WORKER.checkLimit(userId, feature) ────────▶ Billing Worker │
│                                                             │
│  Job Coordinator Worker                                     │
│   env.MEDIA_WORKER.generateChordDiagram(chord) ──────────▶ Media Worker  │
│   env.NOTIFY_WORKER.sendPush(userId, msg) ───────────────▶ Notify Worker │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                ↕ zero public-internet traversal
         All calls stay within Cloudflare's network
```

---

## HTTP-Style Service Binding (Basic)

```typescript
// wrangler.toml (caller side)
// [[services]]
// binding = "AUTH_WORKER"
// service = "auth-service"

// Caller Worker
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const jwt = request.headers.get('Authorization')?.replace('Bearer ', '');

    // Call auth Worker as if making an HTTP request — no domain needed
    const authRes = await env.AUTH_WORKER.fetch(
      new Request('https://internal/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: jwt }),
      })
    );

    if (!authRes.ok) return new Response('Unauthorized', { status: 401 });

    const { userId, roles } = await authRes.json<{ userId: string; roles: string[] }>();
    // Continue with authenticated request...
    return handleRequest(request, userId, roles, env);
  },
};
```

---

## Typed RPC with WorkerEntrypoint (Preferred)

```typescript
// auth-service/src/index.ts  (called Worker — exports a class)
import { WorkerEntrypoint } from 'cloudflare:workers';

interface TokenClaims {
  userId: string;
  roles: string[];
  expiresAt: number;
}

export class AuthService extends WorkerEntrypoint {
  // RPC method — directly callable by name from bindings
  async verifyToken(token: string): Promise<TokenClaims | null> {
    try {
      const claims = await verifyJWT(token, this.env.JWT_SECRET);
      if (claims.expiresAt < Date.now() / 1000) return null;
      return claims;
    } catch {
      return null;
    }
  }

  async issueToken(userId: string, roles: string[]): Promise<string> {
    return signJWT({ userId, roles }, this.env.JWT_SECRET, { expiresIn: '1h' });
  }

  // HTTP fallback — required when the Worker also has a route
  async fetch(request: Request): Promise<Response> {
    return new Response('Auth service — use RPC binding', { status: 200 });
  }
}

// wrangler.toml for auth-service
// main = "src/index.ts"
// [[ ... ]]  migrations etc.
```

```typescript
// api-gateway/src/index.ts  (caller Worker)
import type { AuthService } from '../../auth-service/src/index';

interface Env {
  // Type the binding using the exported class — Workers RPC provides full TS types
  AUTH_SERVICE: Service<AuthService>;
  BILLING_SERVICE: Service<BillingService>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const jwt = request.headers.get('Authorization')?.slice(7) ?? '';

    // Direct method call — no JSON.stringify, no URL construction
    const claims = await env.AUTH_SERVICE.verifyToken(jwt);
    if (!claims) return new Response('Unauthorized', { status: 401 });

    const allowed = await env.BILLING_SERVICE.checkFeatureLimit(
      claims.userId, 'chord-export'
    );
    if (!allowed) return new Response('Upgrade required', { status: 402 });

    return handleRequest(request, claims, env);
  },
};
```

```toml
# api-gateway/wrangler.toml
name = "api-gateway"
main = "src/index.ts"

[[services]]
binding = "AUTH_SERVICE"
service = "auth-service"
entrypoint = "AuthService"  # Required when the Worker exports multiple entrypoints

[[services]]
binding = "BILLING_SERVICE"
service = "billing-service"
entrypoint = "BillingService"
```

---

## Passing Streams and Large Payloads

Workers RPC supports `ReadableStream` as an argument or return value — useful for
streaming audio data to a media Worker without buffering the entire file:

```typescript
// media-service/src/index.ts
import { WorkerEntrypoint } from 'cloudflare:workers';

export class MediaService extends WorkerEntrypoint {
  async transcodeAudio(
    inputStream: ReadableStream<Uint8Array>,
    outputFormat: 'mp3' | 'ogg'
  ): Promise<ReadableStream<Uint8Array>> {
    // Process stream with FFmpeg WASM or pass to R2
    const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
    this.ctx.waitUntil(processStream(inputStream, writable, outputFormat));
    return readable;
  }
}
```

```typescript
// caller Worker
const audioStream = request.body!; // ReadableStream from client upload
const transcodedStream = await env.MEDIA_SERVICE.transcodeAudio(audioStream, 'mp3');
return new Response(transcodedStream, {
  headers: { 'Content-Type': 'audio/mpeg' },
});
```

---

## Multi-level Call Chains

```
Client
  │  POST /v1/export/chord-pack
  ▼
API Gateway Worker
  │  verifyToken()  ──▶  Auth Service
  │  checkLimit()   ──▶  Billing Service
  │  generatePack() ──▶  Export Worker
                              │  generateDiagram(chord) ──▶  Media Worker
                              │  storeAsset(data)        ──▶  R2 (binding)
                              │  notifyUser(userId)      ──▶  Notify Worker
                              ▼
                         Return download URL
```

Service bindings support chaining: a called Worker can itself hold service bindings
to other Workers. Each hop stays within Cloudflare's network. The maximum call depth
is 32 hops (as of 2025). Circular bindings are not allowed.

---

## Error Handling and Observability

```typescript
// Typed errors propagate across RPC boundaries
export class BillingService extends WorkerEntrypoint {
  async checkFeatureLimit(userId: string, feature: string): Promise<boolean> {
    const plan = await this.env.DB
      .prepare('SELECT plan FROM users WHERE id = ?')
      .bind(userId)
      .first<{ plan: string }>();

    if (!plan) throw new Error(`User ${userId} not found`);
    return isFeatureAllowed(plan.plan, feature);
  }
}

// Caller catches the error
try {
  const allowed = await env.BILLING_SERVICE.checkFeatureLimit(userId, 'export');
} catch (err) {
  // err.message is 'User xyz not found' — the string propagates
  console.error('Billing check failed:', err.message);
  return new Response('Service error', { status: 500 });
}
```

Trace IDs propagate automatically across service binding calls when using Cloudflare
Trace (Tail Workers). Log a correlation ID on the gateway and it appears in all called
Workers' logs without any explicit propagation code.

---

## Internal-only Workers (No Public Route)

Workers that are only called via service bindings should have no routes and no triggers.
This prevents accidental public access:

```toml
# notify-service/wrangler.toml
name = "notify-service"
main = "src/index.ts"
# No routes, no triggers — internal only
# Accessible ONLY through service bindings from other Workers
```

---

## Mobile API Consumer Considerations (example project React Native)

Service bindings are invisible to the mobile client. The app sends requests to a single
public hostname (e.g., `api.example.com`), and the API Gateway Worker internally fans
out to specialised Workers via bindings. This means:

- The mobile app does not need to know about internal service topology
- Internal refactors (splitting a monolith Worker, adding a new Worker) are transparent
- API versioning lives at the gateway; internal Workers can evolve independently
- Rate limiting and auth are enforced once at the gateway, not duplicated in each Worker

```
React Native App
    │  POST https://api.example.com/v1/chords/export
    │  Authorization: Bearer <JWT>
    ▼
API Gateway Worker  (public route: api.example.com/*)
    │  verifyToken(jwt)  ──▶  Auth Worker    (internal)
    │  checkLimit(uid)   ──▶  Billing Worker (internal)
    │  export(payload)   ──▶  Export Worker  (internal)
    ▼
Response to app
```

---

## Anti-patterns

- **Using HTTP fetch with `https://worker.account.workers.dev`**: This is public-internet
  routing. It adds latency, incurs egress, and is publicly accessible. Always use
  service bindings for internal calls.
- **Sharing a single monolithic Worker with giant switch-cases**: While valid, it
  creates deployment coupling. Service bindings allow independent deployment of each
  capability.
- **Putting auth logic inside every Worker**: Centralise auth in an Auth Worker called
  via binding from the gateway. Individual Workers trust the gateway.
- **Returning large JSON blobs over RPC**: Prefer streaming (`ReadableStream`) for
  payloads > 10 MB. RPC has a 2 GB structured-clone limit but serialisation overhead
  is non-trivial for large blobs.
- **Circular service bindings**: Worker A → Worker B → Worker A will throw a runtime
  error. Design a clear dependency graph.

---

## Gotchas

- The `entrypoint` field in `wrangler.toml` is required if the called Worker exports
  more than one class or uses a named export other than `default`.
- Workers RPC arguments must be serialisable by the structured clone algorithm.
  Functions, Promises, and class instances with methods do NOT clone — pass plain data
  or streams.
- When developing locally with `wrangler dev`, both Workers must be running simultaneously.
  Use `wrangler dev --local` with multiple terminal sessions or a local service binding
  proxy defined in `wrangler.toml`.
- The called Worker's `env` is its own environment, not the caller's. Secrets are
  not shared; each Worker has its own binding declarations.
- CPU time is counted per Worker in the call chain. A 30-second CPU limit applies to
  each Worker independently — the calling Worker's budget does not transfer.

---

## Verification

```bash
# Run both Workers locally
# Terminal 1: wrangler dev --config auth-service/wrangler.toml --port 8787
# Terminal 2: wrangler dev --config api-gateway/wrangler.toml --port 8788

# Test the RPC call through the gateway
curl -X POST http://localhost:8788/v1/verify \
  -H "Authorization: Bearer <test-jwt>"

# Confirm no outbound network call was made to auth-service.workers.dev
# Check wrangler dev logs — auth service logs should show the inbound call

# Verify internal worker is not publicly reachable
curl https://notify-service.account.workers.dev/
# Expected: 403 Forbidden (no route configured)
```

---

## Related

- `api-gateway-pattern-cloudflare-workers.md` — gateway pattern using service bindings
- `edge-first-architecture-patterns.md` — edge decomposition strategies
- `competing-consumers-durable-objects.md` — Durable Object inter-Worker calls
- `oauth-architecture.md` — JWT issuing and verification
- `secret-management-architecture.md` — per-Worker secrets management
- `observability-architecture.md` — distributed tracing across Workers

---

## Sources

- Cloudflare Service Bindings documentation (developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings)
- Cloudflare Workers RPC documentation (developers.cloudflare.com/workers/runtime-apis/rpc)
- WorkerEntrypoint class reference
- Structured Clone Algorithm — MDN Web Docs
