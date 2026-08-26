# Cloudflare Pages Functions — Session Validation Middleware

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project issues anonymous ephemeral session tokens (JWT or HMAC-signed opaque tokens) so
users can take actions (post, vote, comment) without creating an account. Every API route
under `/functions/api/` must validate this token and reject requests with expired or forged
sessions before they touch D1 or KV. Duplicating validation logic in each route handler
leads to drift. Pages Functions middleware (`_middleware.ts`) centralises it.

## Context

Cloudflare Pages Functions support a `_middleware.ts` file at any directory level. The file
exports an `onRequest` handler (or an array) that runs before any route handler in that
directory tree. Middleware receives a `PluginData` context with `next()` to continue the chain.
Session tokens on example project are JWT RS256 tokens issued by a Cloudflare Worker (`auth-worker`)
and stored in an `HttpOnly; Secure; SameSite=Strict` cookie named `wam_session`.

## Middleware File Structure

```
functions/
  api/
    _middleware.ts      ← session validation for all /api/* routes
    feed.ts
    post/
      [id].ts
      vote.ts
    _middleware.ts      ← (optional) per-subdirectory stricter rules
  _middleware.ts        ← global: logging, CORS headers
```

## Global Middleware: CORS + Request ID

```typescript
// functions/_middleware.ts
export const onRequest: PagesFunction = async (ctx) => {
  const requestId = crypto.randomUUID();
  ctx.data.requestId = requestId;

  const response = await ctx.next();

  // Attach CORS and trace headers to every response
  const headers = new Headers(response.headers);
  headers.set("X-Request-Id", requestId);
  headers.set("Access-Control-Allow-Origin", "https://example.com");
  headers.set("Access-Control-Allow-Credentials", "true");

  return new Response(response.body, { status: response.status, headers });
};
```

## API Middleware: JWT Session Validation

```typescript
// functions/api/_middleware.ts
import { verifyJwt, JwtPayload } from "../../src/lib/jwt";

export const onRequest: PagesFunction<Env> = async (ctx) => {
  // Allow preflight through without validation
  if (ctx.request.method === "OPTIONS") return ctx.next();

  const cookie = parseCookie(ctx.request.headers.get("Cookie") ?? "");
  const token = cookie["wam_session"];

  if (!token) {
    return jsonError(401, "Missing session token", ctx.data.requestId);
  }

  let session: JwtPayload;
  try {
    session = await verifyJwt(token, ctx.env.JWT_PUBLIC_KEY);
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Invalid token";
    return jsonError(401, msg, ctx.data.requestId);
  }

  // Check session is not revoked (KV tombstone set on logout/ban)
  const revoked = await ctx.env.SESSION_KV.get(`revoked:${session.jti}`);
  if (revoked !== null) {
    return jsonError(401, "Session revoked", ctx.data.requestId);
  }

  // Attach validated session to context data for downstream handlers
  ctx.data.session = session;
  return ctx.next();
};

function parseCookie(header: string): Record<string, string> {
  return Object.fromEntries(
    header.split(";").map((part) => {
      const [k, ...v] = part.trim().split("=");
      return [k.trim(), decodeURIComponent(v.join("="))];
    })
  );
}

function jsonError(status: number, message: string, requestId?: string): Response {
  return new Response(JSON.stringify({ error: message, requestId }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

interface Env {
  SESSION_KV: KVNamespace;
  JWT_PUBLIC_KEY: string;
}
```

## JWT Verification Library (Web Crypto)

```typescript
// src/lib/jwt.ts  — runs in Workers / Pages Functions (no Node.js)
export interface JwtPayload {
  sub: string;   // anonymous user ID
  jti: string;   // unique token ID for revocation
  exp: number;
  iat: number;
  role: "anon" | "member";
}

export async function verifyJwt(token: string, publicKeyPem: string): Promise<JwtPayload> {
  const [headerB64, payloadB64, sigB64] = token.split(".");
  if (!headerB64 || !payloadB64 || !sigB64) throw new Error("Malformed JWT");

  const key = await importPublicKey(publicKeyPem);
  const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const sig = base64UrlDecode(sigB64);

  const valid = await crypto.subtle.verify({ name: "RSASSA-PKCS1-v1_5" }, key, sig, data);
  if (!valid) throw new Error("Invalid signature");

  const payload: JwtPayload = JSON.parse(atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/")));

  if (payload.exp < Math.floor(Date.now() / 1000)) throw new Error("Token expired");
  return payload;
}

async function importPublicKey(pem: string): Promise<CryptoKey> {
  const pemContent = pem.replace(/-----[^-]+-----/g, "").replace(/\s/g, "");
  const der = Uint8Array.from(atob(pemContent), (c) => c.charCodeAt(0));
  return crypto.subtle.importKey(
    "spki",
    der,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"]
  );
}

function base64UrlDecode(str: string): Uint8Array {
  return Uint8Array.from(atob(str.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
}
```

## Consuming Session Data in a Route Handler

```typescript
// functions/api/post/vote.ts
interface Env { DB: D1Database; }

export const onRequestPost: PagesFunction<Env> = async (ctx) => {
  // Middleware has already validated the session and attached it to ctx.data
  const { session } = ctx.data as { session: import("../../../src/lib/jwt").JwtPayload };
  const { postId, direction } = await ctx.request.json<{ postId: string; direction: 1 | -1 }>();

  await ctx.env.DB.prepare(
    "INSERT OR REPLACE INTO votes (post_id, voter_id, direction) VALUES (?, ?, ?)"
  ).bind(postId, session.sub, direction).run();

  return new Response(JSON.stringify({ ok: true }), {
    headers: { "Content-Type": "application/json" },
  });
};
```

## Rate-Limiting Layer (Optional Second Middleware)

```typescript
// functions/api/_middleware.ts — extend with rate limiting after session check
const RATE_LIMIT_WINDOW = 60;  // seconds
const RATE_LIMIT_MAX    = 100; // requests per window

async function checkRateLimit(sub: string, kv: KVNamespace): Promise<boolean> {
  const key = `rl:${sub}:${Math.floor(Date.now() / 1000 / RATE_LIMIT_WINDOW)}`;
  const raw = await kv.get(key);
  const count = raw ? parseInt(raw) + 1 : 1;
  await kv.put(key, String(count), { expirationTtl: RATE_LIMIT_WINDOW * 2 });
  return count <= RATE_LIMIT_MAX;
}
```

## Anti-patterns

- **Putting auth logic in individual route handlers** — A missed check exposes the endpoint;
  use middleware to enforce it uniformly.
- **Storing full session state in the JWT** — Keep the payload minimal (`sub`, `jti`, `exp`);
  fetch additional claims from KV inside handlers.
- **Skipping revocation checks for performance** — Revocation matters most on logout and
  account-suspension flows; cache the KV lookup with a short TTL if needed.
- **Using `localStorage` to pass the session token to the API** — Always use `HttpOnly`
  cookies; JS-accessible tokens are XSS targets.

## Gotchas

- Pages Functions middleware runs **only for requests routed to Functions**, not for static
  asset serving; do not rely on it to block static file access.
- `ctx.data` is typed as `Record<string, unknown>` by default; cast or augment the type in a
  `d.ts` file for type safety across the middleware chain.
- KV `get()` adds ~5–15 ms of latency per call; use `cacheTtl` option (`kv.get(key, { cacheTtl: 30 })`) for revocation checks on hot paths.
- `_middleware.ts` at `functions/api/` applies to `functions/api/post/vote.ts` — nesting is
  inclusive; you do not need to duplicate middleware in subdirectories.

## Verification

```bash
# Test unauthenticated request
curl -s https://example.com/api/feed | jq .error
# → "Missing session token"

# Test with valid cookie
curl -s -b "wam_session=<valid_jwt>" https://example.com/api/feed | jq .posts | wc -l

# Tail live middleware errors
npx wrangler pages deployment tail --project-name=example project
```

## Related

- `cloudflare-pages-middleware-auth-gating.md`
- `cloudflare-pages-ab-testing-cookie-split.md`
- `feature-flags-cloudflare-workers-kv-edge-config.md`
- `web-crypto-api-client-side-encryption-cloudflare-pages.md`
- `credential-management-api-cloudflare-workers.md`

## Sources

- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/pages/functions/api-reference/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
