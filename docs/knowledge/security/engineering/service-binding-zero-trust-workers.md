# Service Binding Zero-Trust Security in Workers

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

You have decomposed your Cloudflare Workers backend into multiple Workers — an API gateway, an auth Worker, a payments Worker, a notification Worker — and you use service bindings to let them call each other directly without going over the public internet. A developer assumes these internal Worker-to-Worker calls are inherently trusted because they never leave Cloudflare's network. Six months later a bug in the public-facing Worker allows an attacker to call the payments Worker's internal `POST /charge` endpoint by manipulating the routing logic, or a newly added Worker is bound to the payments Worker without security review and can call it without restriction.

Service bindings are not a security boundary. They are a performance and availability primitive. Zero-trust principles — verify every caller, enforce least-privilege, audit every call — must be applied to service bindings explicitly.

---

## Context

A Cloudflare Workers **service binding** lets one Worker invoke another Worker in the same account synchronously, without an HTTP round-trip to the public internet. The called Worker receives a `Request` object constructed by the calling Worker. Critically:

- The called Worker **cannot verify the caller's identity** from network-layer signals alone. There is no TLS client certificate or mTLS handshake — the binding is a direct function call.
- The called Worker sees `request.headers` as set by the calling Worker. A caller can set any header, including `Authorization`, `X-Internal-Caller`, or `CF-Connecting-IP`.
- **Service bindings bypass Cloudflare Access** by default. Rules you have applied to the Workers route do not apply to service-binding calls.
- A Worker bound to another Worker has full access to call any of its public URL paths unless the called Worker validates the caller.

The solution is to treat every service binding call as an untrusted HTTP request from an external caller and require a cryptographically verified identity assertion.

---

## Architecture: Signed Request Tokens

The calling Worker signs a compact JWT or HMAC-signed token identifying itself. The called Worker verifies the signature before processing the request. The signing key is a shared secret stored via `wrangler secret` in both Workers.

```
[Public Client]
    │
    ▼
[API Gateway Worker]  ──── service binding ────►  [Payments Worker]
    │                       + signed caller token       │
    │                                                   ▼
    │                                         verify signature
    │                                         check caller_id == 'api-gateway'
    │                                         enforce endpoint allowlist
```

---

## Signing Library: Shared Between Workers

```typescript
// packages/service-auth/src/index.ts
// Publish as an internal package or copy into each Worker's src/

export interface ServiceClaims {
  caller_id: string;    // stable identifier for the calling Worker
  target_id: string;    // identifier for the target Worker (prevents token reuse)
  method: string;       // HTTP method the token authorises
  path: string;         // exact path the token authorises
  iat: number;          // issued-at unix timestamp (seconds)
  exp: number;          // expiry unix timestamp (seconds)
  jti: string;          // unique token ID for replay prevention
}

const ALGORITHM = { name: 'HMAC', hash: 'SHA-256' };
const TOKEN_TTL_SECONDS = 30; // very short-lived; replays must happen within this window

async function importKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    ALGORITHM,
    false,
    ['sign', 'verify']
  );
}

function base64url(buffer: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

function base64urlDecode(str: string): ArrayBuffer {
  const padded = str.replace(/-/g, '+').replace(/_/g, '/').padEnd(
    str.length + (4 - (str.length % 4)) % 4,
    '='
  );
  const binary = atob(padded);
  return Uint8Array.from(binary, c => c.charCodeAt(0)).buffer;
}

/**
 * Create a short-lived, path-bound service token.
 * Call this in the upstream Worker immediately before the service binding call.
 */
export async function createServiceToken(
  secret: string,
  callerId: string,
  targetId: string,
  method: string,
  path: string
): Promise<string> {
  const claims: ServiceClaims = {
    caller_id: callerId,
    target_id: targetId,
    method: method.toUpperCase(),
    path,
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + TOKEN_TTL_SECONDS,
    jti: crypto.randomUUID(),
  };

  const header = base64url(new TextEncoder().encode(JSON.stringify({ alg: 'HS256', typ: 'JWT' })));
  const payload = base64url(new TextEncoder().encode(JSON.stringify(claims)));
  const signingInput = `${header}.${payload}`;

  const key = await importKey(secret);
  const signature = await crypto.subtle.sign(
    ALGORITHM,
    key,
    new TextEncoder().encode(signingInput)
  );

  return `${signingInput}.${base64url(signature)}`;
}

export interface VerifyResult {
  valid: boolean;
  claims?: ServiceClaims;
  error?: string;
}

/**
 * Verify a service token in the downstream Worker.
 * Validates signature, expiry, method, path, and target_id.
 */
export async function verifyServiceToken(
  token: string,
  secret: string,
  expectedTargetId: string,
  method: string,
  path: string
): Promise<VerifyResult> {
  const parts = token.split('.');
  if (parts.length !== 3) return { valid: false, error: 'Malformed token' };

  const [header, payload, signature] = parts;
  const signingInput = `${header}.${payload}`;

  const key = await importKey(secret);
  const valid = await crypto.subtle.verify(
    ALGORITHM,
    key,
    base64urlDecode(signature),
    new TextEncoder().encode(signingInput)
  );

  if (!valid) return { valid: false, error: 'Invalid signature' };

  let claims: ServiceClaims;
  try {
    claims = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    return { valid: false, error: 'Invalid payload' };
  }

  const now = Math.floor(Date.now() / 1000);
  if (claims.exp < now) return { valid: false, error: 'Token expired' };
  if (claims.iat > now + 5) return { valid: false, error: 'Token not yet valid (clock skew)' };
  if (claims.target_id !== expectedTargetId) return { valid: false, error: 'Wrong target' };
  if (claims.method !== method.toUpperCase()) return { valid: false, error: 'Method mismatch' };
  if (claims.path !== path) return { valid: false, error: 'Path mismatch' };

  return { valid: true, claims };
}
```

---

## Calling Worker: API Gateway

```typescript
// src/api-gateway/worker.ts
import { createServiceToken } from '../shared/service-auth';

export interface Env {
  PAYMENTS: Fetcher;          // service binding to payments Worker
  SERVICE_SHARED_SECRET: string; // wrangler secret put
  CALLER_ID: string;          // "api-gateway" (non-secret, from [vars])
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === '/api/charge' && request.method === 'POST') {
      return handleCharge(request, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function handleCharge(request: Request, env: Env): Promise<Response> {
  const targetPath = '/internal/charge';
  const method = 'POST';

  // Create a 30-second token bound to this specific method and path
  const token = await createServiceToken(
    env.SERVICE_SHARED_SECRET,
    env.CALLER_ID,           // 'api-gateway'
    'payments-worker',
    method,
    targetPath
  );

  // Forward the request to the payments Worker via service binding
  const internalRequest = new Request(
    `https://payments-worker.internal${targetPath}`,
    {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-Service-Token': token,
        // Explicitly do NOT forward the caller's Authorization header here;
        // re-authenticate using the service token instead
      },
      body: request.body,
    }
  );

  return env.PAYMENTS.fetch(internalRequest);
}
```

---

## Called Worker: Payments Service

```typescript
// src/payments-worker/worker.ts
import { verifyServiceToken } from '../shared/service-auth';

export interface Env {
  SERVICE_SHARED_SECRET: string;
  TARGET_ID: string; // 'payments-worker' (from [vars])
}

// Allowlist: only these callers may call these paths
const CALLER_ALLOWLIST: Record<string, string[]> = {
  'api-gateway': ['/internal/charge', '/internal/refund'],
  'admin-worker': ['/internal/void', '/internal/reconcile'],
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    // All /internal/* paths require a valid service token
    if (pathname.startsWith('/internal/')) {
      const authResult = await authenticateServiceCall(request, env, pathname);
      if (!authResult.ok) {
        return new Response(JSON.stringify({ error: authResult.error }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      // Enforce caller-to-path allowlist
      const callerId = authResult.callerId!;
      const allowedPaths = CALLER_ALLOWLIST[callerId] ?? [];
      if (!allowedPaths.includes(pathname)) {
        return new Response(
          JSON.stringify({ error: `Caller ${callerId} not authorised for ${pathname}` }),
          { status: 403, headers: { 'Content-Type': 'application/json' } }
        );
      }
    }

    // Route to handler
    if (pathname === '/internal/charge' && request.method === 'POST') {
      return handleCharge(request, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function authenticateServiceCall(
  request: Request,
  env: Env,
  pathname: string
): Promise<{ ok: boolean; callerId?: string; error?: string }> {
  const token = request.headers.get('X-Service-Token');
  if (!token) return { ok: false, error: 'Missing X-Service-Token' };

  const result = await verifyServiceToken(
    token,
    env.SERVICE_SHARED_SECRET,
    env.TARGET_ID,
    request.method,
    pathname
  );

  if (!result.valid) return { ok: false, error: result.error };

  return { ok: true, callerId: result.claims!.caller_id };
}

async function handleCharge(request: Request, _env: Env): Promise<Response> {
  // ... payment processing logic ...
  return Response.json({ status: 'charged' });
}
```

---

## Audit Logging Service Binding Calls

```typescript
// src/payments-worker/audit.ts
import type { D1Database } from '@cloudflare/workers-types';

export async function logServiceCall(
  db: D1Database,
  callerId: string,
  path: string,
  method: string,
  statusCode: number,
  jti: string
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO service_call_audit
         (jti, caller_id, path, method, status_code, called_at)
       VALUES (?, ?, ?, ?, ?, unixepoch('now') * 1000)`
    )
    .bind(jti, callerId, path, method, statusCode)
    .run();
}

// Schema (run in D1 migrations):
// CREATE TABLE service_call_audit (
//   jti         TEXT PRIMARY KEY,          -- prevents replay: jti must be unique
//   caller_id   TEXT NOT NULL,
//   path        TEXT NOT NULL,
//   method      TEXT NOT NULL,
//   status_code INTEGER NOT NULL,
//   called_at   INTEGER NOT NULL
// );
// CREATE INDEX idx_service_audit_caller ON service_call_audit (caller_id, called_at DESC);
```

---

## Anti-patterns

**Trusting `X-Internal-Caller` header without cryptographic verification.** Any Worker that has a service binding can set any header value. An attacker who controls any bound Worker can spoof a caller ID. Verify using HMAC signatures, never header values alone.

**Using a single shared secret across all Worker pairs.** A compromised Worker can then impersonate any other Worker. Use one shared secret per calling-Worker/target-Worker pair, stored separately in each Worker's secrets.

**Binding development/staging Workers to production Workers.** A service binding granted to a staging Worker gives staging-Worker code access to the production target. Use separate Cloudflare accounts or namespace prefixes for environments.

**Not expiring tokens.** Service tokens that are valid for hours rather than seconds are vulnerable to replay attacks if an intermediate service (a logging worker, a proxy) captures the `X-Service-Token` header. Keep TTL at 30–60 seconds.

**Skipping the `jti` uniqueness check.** Even a short TTL is vulnerable to replay within that window. Store `jti` in D1 or KV and reject tokens whose `jti` has already been seen.

---

## Gotchas

**Service bindings bypass `wrangler.toml` route filters and Cloudflare Access rules.** Rules applied to `https://payments.example.com/*` do not apply to `env.PAYMENTS.fetch(...)`. You must implement your own auth middleware inside the Worker.

**The `Host` header in service binding requests is set by the calling Worker.** Do not use `request.headers.get('Host')` in the called Worker to identify the caller — it is caller-controlled.

**Service bindings can chain across Workers.** Worker A → Worker B → Worker C via nested bindings. Each hop requires its own token. Do not pass Worker A's token to Worker C.

**Replay prevention via D1 `jti` storage adds a write on every call.** For high-throughput internal paths, consider a Durable Object as a `jti` replay window store — it offers lower-latency strongly-consistent writes without D1 connection overhead.

**Service binding errors surface as fetch exceptions in the calling Worker.** Wrap `env.SERVICE.fetch()` in try/catch and handle network-level errors (500, timeout) separately from authentication failures (401, 403) in the called Worker's response.

---

## Verification

```bash
# 1. Verify the payments Worker rejects requests without a service token
curl -s -X POST https://payments-worker.example.com/internal/charge \
  -H "Content-Type: application/json" \
  -d '{"amount": 100}' | jq .
# Expected: {"error":"Missing X-Service-Token"}  HTTP 401

# 2. Verify an expired token is rejected
# (Generate a token, wait 31 seconds, then call with it)
# Expected: {"error":"Token expired"}  HTTP 401

# 3. Verify a wrong-path token is rejected
# Generate a token for /internal/refund and use it on /internal/charge
# Expected: {"error":"Path mismatch"}  HTTP 401

# 4. Verify audit log records every call
wrangler d1 execute payments-db \
  --command "SELECT caller_id, path, status_code FROM service_call_audit ORDER BY called_at DESC LIMIT 5"
```

---

## Related

- `durable-objects-auth-patterns.md` — authenticating callers within Durable Objects
- `jwt-best-practices.md` — JWT signing and validation fundamentals
- `audit-log-security.md` — structuring audit logs for compliance
- `multi-tenancy-isolation-workers-kv-d1.md` — isolating data across tenant Workers
- `zero-trust-network-architecture-ztna.md` — zero-trust principles applied to service meshes

---

## Sources

- Cloudflare Workers Service Bindings documentation: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Zero Trust Architecture, NIST SP 800-207 §3.3 — "Never Trust, Always Verify": https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-207.pdf
- RFC 7519 — JSON Web Tokens (JWT), §4.1.7 (`jti` claim): https://www.rfc-editor.org/rfc/rfc7519#section-4.1.7
- Web Crypto API HMAC: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign
- Cloudflare service bindings and Cloudflare Access: https://developers.cloudflare.com/cloudflare-one/identity/service-auth/service-tokens/
