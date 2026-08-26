# Building Internal Microservice APIs with Workers Service Bindings

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have multiple Cloudflare Workers that need to call each other without going over the public internet, without adding latency from an extra HTTP round-trip, and without exposing internal endpoints to unauthenticated traffic. Service bindings let one Worker invoke another directly inside Cloudflare's network, passing a `Request` object and receiving a `Response` — zero egress, sub-millisecond overhead.

---

## Context

Service bindings were GA'd in 2022 and are declared in `wrangler.toml` under `[[services]]`. The calling Worker receives the callee as a `Fetcher` object on `env`, and calls it with the same `fetch` signature it already knows. Because the call is in-process (same isolate group), there is no TLS handshake and no DNS lookup. Local development requires `wrangler dev --service AUTH_SERVICE=./auth-worker` so Wrangler spawns both workers and wires the binding. Type contracts between services are kept in a shared TypeScript package published to npm or referenced via a workspace monorepo.

---

## Section 1 — Config / wrangler.toml

```toml
# gateway-worker/wrangler.toml
name = "gateway-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[services]]
binding = "AUTH_SERVICE"
service = "auth-worker"

[[services]]
binding = "PROFILE_SERVICE"
service = "profile-worker"

[vars]
ENV = "production"
```

```toml
# auth-worker/wrangler.toml
name = "auth-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"
```

---

## Section 2 — Shared type contracts

```typescript
// packages/contracts/src/auth.ts
export interface AuthRequest {
  token: string;
}

export interface AuthResponse {
  ok: boolean;
  userId?: string;
  error?: string;
}

export interface ProfileRequest {
  userId: string;
}

export interface ProfileResponse {
  userId: string;
  displayName: string;
  avatarUrl: string;
}

// Helper — build a typed internal Request
export function buildInternalRequest(
  path: string,
  body: unknown,
  baseUrl = "https://internal"
): Request {
  return new Request(`${baseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// Helper — parse a typed internal Response, throw on non-2xx
export async function parseInternalResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Internal service error ${res.status}: ${text}`);
  }
  return res.json<T>();
}
```

---

## Section 3 — Gateway Worker calling downstream services

```typescript
// gateway-worker/src/index.ts
import {
  AuthRequest,
  AuthResponse,
  ProfileRequest,
  ProfileResponse,
  buildInternalRequest,
  parseInternalResponse,
} from "@example-org/example-repo/auth";

export interface Env {
  AUTH_SERVICE: Fetcher;
  PROFILE_SERVICE: Fetcher;
}

async function authenticate(env: Env, token: string): Promise<AuthResponse> {
  const req = buildInternalRequest<AuthRequest>("/verify", { token });
  const res = await env.AUTH_SERVICE.fetch(req);
  return parseInternalResponse<AuthResponse>(res);
}

async function getProfile(env: Env, userId: string): Promise<ProfileResponse> {
  const req = buildInternalRequest<ProfileRequest>("/profile", { userId });
  const res = await env.PROFILE_SERVICE.fetch(req);
  return parseInternalResponse<ProfileResponse>(res);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const authHeader = request.headers.get("Authorization") ?? "";
    const token = authHeader.replace(/^Bearer\s+/, "");
    if (!token) {
      return new Response(JSON.stringify({ error: "Missing token" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }

    let auth: AuthResponse;
    try {
      auth = await authenticate(env, token);
    } catch (err) {
      return new Response(JSON.stringify({ error: "Auth service unavailable" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (!auth.ok || !auth.userId) {
      return new Response(JSON.stringify({ error: auth.error ?? "Unauthorized" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    }

    const profile = await getProfile(env, auth.userId);
    return new Response(JSON.stringify(profile), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

```typescript
// auth-worker/src/index.ts
import type { AuthRequest, AuthResponse } from "@example-org/example-repo/auth";

export default {
  async fetch(request: Request): Promise<Response> {
    if (new URL(request.url).pathname !== "/verify") {
      return new Response("Not found", { status: 404 });
    }
    const { token } = await request.json<AuthRequest>();
    // Replace with real JWT validation
    const ok = token.startsWith("valid-");
    const body: AuthResponse = ok
      ? { ok: true, userId: token.slice(6) }
      : { ok: false, error: "Invalid token" };
    return new Response(JSON.stringify(body), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## Anti-patterns

- **Calling the public URL instead of the binding** — This adds latency, egress costs, and requires auth on the receiving side; always use `env.SERVICE.fetch()` for internal calls.
- **Omitting error propagation** — Swallowing non-2xx responses silently produces confusing 200s downstream; always check `res.ok` and surface the upstream status.
- **Sharing mutable state via global variables** — Service bindings run in the same isolate group but do not share memory; use Durable Objects or KV for shared state.
- **Hardcoding `https://internal` URLs in production** — The hostname is irrelevant for service bindings (Cloudflare ignores it) but a consistent internal-only convention prevents accidentally routing real HTTP traffic.

---

## Gotchas

- Service bindings do **not** count against your outbound request budget — they are free subrequests capped at 1000/request like `fetch()`.
- The callee Worker must be **deployed** before the caller can be deployed; CI pipelines must order deployments by dependency.
- `wrangler dev --service` only works if both worker directories are on the same machine; in CI use `wrangler dev --remote` with deployed workers.
- Circular bindings (A calls B, B calls A) are allowed but can cause infinite loops; add depth headers to guard against them.
- The `Fetcher` type is only available in `@cloudflare/workers-types`; add it to `tsconfig.json` under `types`.

---

## Verification

```bash
# Local dev — start gateway, wiring in the auth worker from its local directory
npx wrangler dev --config gateway-worker/wrangler.toml \
  --service AUTH_SERVICE=./auth-worker \
  --service PROFILE_SERVICE=./profile-worker

# Smoke test
curl -H "Authorization: Bearer valid-user42" http://localhost:8787/
# Expected: {"userId":"user42","displayName":"...","avatarUrl":"..."}

curl -H "Authorization: Bearer bad-token" http://localhost:8787/
# Expected: {"error":"Invalid token"} with status 403

# Deploy in dependency order
npx wrangler deploy --config auth-worker/wrangler.toml
npx wrangler deploy --config profile-worker/wrangler.toml
npx wrangler deploy --config gateway-worker/wrangler.toml
```

---

## Related

- `workers-durable-objects-websocket-rooms.md`
- `workers-geo-routing-cf-request.md`

---

## Sources

- Cloudflare Docs: Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Blog: Zero-latency service-to-service calls — https://blog.cloudflare.com/service-bindings-general-availability/
