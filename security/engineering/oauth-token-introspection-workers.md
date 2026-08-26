# OAuth 2.0 Token Introspection Endpoint on Workers (RFC 7662)

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Resource servers need to validate opaque Bearer tokens issued by an authorization server without
sharing the signing secret or replicating a full token database to every edge node. A centralised
token introspection endpoint (RFC 7662) exposed on Cloudflare Workers lets downstream services
verify token liveness, scope, and revocation status with a single protected HTTP POST.

## Context

Cloudflare Workers can act as a lightweight OAuth 2.0 introspection proxy: it receives the
`token` parameter, looks up the token record in D1 or KV, and returns the standard
`active`/`scope`/`sub` JSON body. Because the introspection endpoint itself is a protected
resource (callers must present their own `client_credentials` Bearer token), the Worker must
authenticate the *caller* before it can answer questions about the *subject* token. Cloudflare
Access policies or service binding tokens enforce caller authentication at the edge before the
Worker code even runs.

## Threat Model

**Attacker goal**: enumerate valid access tokens, probe revocation state, or pivot from a
compromised resource server credential to learn about other clients.

Attack scenarios:

- **Token fishing**: unauthenticated callers POST arbitrary strings and observe `active: true`
  to confirm valid tokens — effectively an oracle for brute-forcing short tokens.
- **Introspection replay**: a resource server credential is stolen; the attacker reuses it to
  introspect all tokens issued to high-privilege clients.
- **Response forgery**: a man-in-the-middle returns crafted `active: true` payloads to a
  resource server that does not validate the TLS chain or the response signature.
- **Information leakage**: the response body includes `sub`, `scope`, `client_id`, and
  `username` — over-broad caller ACLs expose PII to every resource server in the fleet.

## Implementation — Introspection Endpoint Worker

```typescript
// introspection-worker/src/index.ts
import { D1Database, KVNamespace } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  TOKEN_CACHE: KVNamespace;
  // Pre-shared secret for resource-server callers (store in Workers secrets, not vars)
  INTROSPECTION_CLIENT_SECRET: string;
  // Comma-separated list of allowed client_ids for introspection
  INTROSPECTION_ALLOWED_CLIENTS: string;
}

interface IntrospectionResponse {
  active: boolean;
  scope?: string;
  client_id?: string;
  username?: string;
  token_type?: string;
  exp?: number;
  iat?: number;
  sub?: string;
  aud?: string;
  iss?: string;
  jti?: string;
}

// Constant-time string comparison to prevent timing attacks
async function timingSafeEqual(a: string, b: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const aBytes = encoder.encode(a);
  const bBytes = encoder.encode(b);
  // Pad shorter to same length before importing — we compare digests, not raw strings
  const aKey = await crypto.subtle.importKey(
    'raw', aBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const bKey = await crypto.subtle.importKey(
    'raw', bBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sentinel = new TextEncoder().encode('introspection-sentinel');
  const [aSig, bSig] = await Promise.all([
    crypto.subtle.sign('HMAC', aKey, sentinel),
    crypto.subtle.sign('HMAC', bKey, sentinel),
  ]);
  return timingSafeEqualBytes(new Uint8Array(aSig), new Uint8Array(bSig));
}

function timingSafeEqualBytes(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

// Authenticate the resource server making the introspection request
async function authenticateCaller(request: Request, env: Env): Promise<string | null> {
  const auth = request.headers.get('Authorization') ?? '';
  if (!auth.startsWith('Basic ')) return null;

  const decoded = atob(auth.slice(6));
  const colon = decoded.indexOf(':');
  if (colon === -1) return null;

  const clientId = decoded.slice(0, colon);
  const clientSecret = <redacted-secret> + 1);

  const allowedClients = env.INTROSPECTION_ALLOWED_CLIENTS.split(',').map(s => s.trim());
  if (!allowedClients.includes(clientId)) return null;

  // Validate secret with constant-time comparison
  const secretValid = await timingSafeEqual(clientSecret, env.INTROSPECTION_CLIENT_SECRET);
  return secretValid ? clientId : null;
}

async function lookupToken(token: string, env: Env): Promise<IntrospectionResponse> {
  // Check short-lived negative cache first to throttle repeated lookups of invalid tokens
  const cacheKey = `introspect:${token}`;
  const cached = await env.TOKEN_CACHE.get(cacheKey, 'json') as IntrospectionResponse | null;
  if (cached !== null) return cached;

  const row = await env.DB.prepare(`
    SELECT
      access_tokens.jti,
      access_tokens.sub,
      access_tokens.scope,
      access_tokens.client_id,
      access_tokens.issued_at,
      access_tokens.expires_at,
      access_tokens.revoked_at,
      users.username
    FROM access_tokens
    LEFT JOIN users ON users.id = access_tokens.sub
    WHERE access_tokens.token_hash = ?1
    LIMIT 1
  `).bind(await hashToken(token)).first<{
    jti: string; sub: string; scope: string; client_id: string;
    issued_at: number; expires_at: number; revoked_at: number | null;
    username: string | null;
  }>();

  const nowSec = Math.floor(Date.now() / 1000);

  if (!row || row.revoked_at !== null || row.expires_at < nowSec) {
    const inactive: IntrospectionResponse = { active: false };
    // Cache negative results for 30 s to blunt brute-force oracles
    await env.TOKEN_CACHE.put(cacheKey, JSON.stringify(inactive), { expirationTtl: 30 });
    return inactive;
  }

  const response: IntrospectionResponse = {
    active: true,
    scope: row.scope,
    client_id: row.client_id,
    sub: row.sub,
    username: row.username ?? undefined,
    token_type: 'Bearer',
    iat: row.issued_at,
    exp: row.expires_at,
    iss: 'https://auth.example.com',
    jti: row.jti,
  };

  // Cache active results for 60 s — keep TTL short so revocation propagates quickly
  await env.TOKEN_CACHE.put(cacheKey, JSON.stringify(response), { expirationTtl: 60 });
  return response;
}

async function hashToken(token: string): Promise<string> {
  const data = new TextEncoder().encode(token);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only POST is allowed — GET would expose the token in server logs
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', {
        status: 405,
        headers: { Allow: 'POST', 'Content-Type': 'application/json' },
      });
    }

    // Enforce application/x-www-form-urlencoded content type per RFC 7662 §2.1
    const ct = request.headers.get('Content-Type') ?? '';
    if (!ct.includes('application/x-www-form-urlencoded')) {
      return Response.json({ error: 'invalid_request' }, { status: 400 });
    }

    // Step 1: authenticate the resource server caller
    const callerId = await authenticateCaller(request, env);
    if (!callerId) {
      return new Response(JSON.stringify({ error: 'unauthorized_client' }), {
        status: 401,
        headers: {
          'Content-Type': 'application/json',
          'WWW-Authenticate': 'Basic realm="token_introspection"',
        },
      });
    }

    // Step 2: extract the token parameter
    const body = await request.formData();
    const token = body.get('token');
    if (!token || typeof token !== 'string') {
      return Response.json({ error: 'invalid_request', error_description: 'token is required' }, { status: 400 });
    }

    // Reject tokens that are suspiciously long (>2 KB) to prevent hash-DoS
    if (token.length > 2048) {
      return Response.json({ active: false });
    }

    // Step 3: look up and return introspection result
    const result = await lookupToken(token, env);

    // Per RFC 7662 §2.2, filter response fields based on caller's authorisation level
    // (here: only privileged callers receive username/sub)
    const privilegedClients = ['internal-api-gateway', 'admin-resource-server'];
    if (!privilegedClients.includes(callerId) && result.active) {
      delete result.username;
      delete result.sub;
    }

    return Response.json(result, {
      headers: {
        // Introspection responses must not be cached by intermediaries
        'Cache-Control': 'no-store',
        Pragma: 'no-cache',
      },
    });
  },
};
```

## Hardening — Revocation Propagation via Queues

```typescript
// When a token is revoked (logout, password change), publish to a Cloudflare Queue
// so the KV introspection cache is immediately invalidated across all edge nodes.
import { Queue } from '@cloudflare/workers-types';

export interface RevocationEnv {
  TOKEN_CACHE: KVNamespace;
  REVOCATION_QUEUE: Queue<{ tokenHash: string }>;
}

// Token issuer calls this to revoke a token
export async function revokeToken(tokenHash: string, env: RevocationEnv): Promise<void> {
  // Immediately delete from KV cache — next introspection hits D1 and sees revoked_at
  await env.TOKEN_CACHE.delete(`introspect:${tokenHash}`);
  // Fan out to all regions via Queue consumer if needed
  await env.REVOCATION_QUEUE.send({ tokenHash });
}

// Queue consumer — run in every region to purge stale cached introspection results
export const queueHandler = {
  async queue(batch: MessageBatch<{ tokenHash: string }>, env: RevocationEnv): Promise<void> {
    await Promise.all(
      batch.messages.map(msg => env.TOKEN_CACHE.delete(`introspect:${msg.body.tokenHash}`))
    );
    batch.ackAll();
  },
};
```

## Anti-patterns

- **Unauthenticated introspection endpoint**: omitting caller authentication turns the endpoint
  into a token-validity oracle that any attacker can query.
- **Storing raw tokens**: always store SHA-256 hashes of tokens in D1; a database breach must
  not expose usable Bearer tokens.
- **Long cache TTL on active tokens**: caching active results for more than 60–120 s means
  revoked tokens remain accepted at resource servers for that window.
- **GET method for introspection**: the token appears in the URL and ends up in access logs,
  CDN logs, and `Referer` headers — always use POST with a form body.
- **Returning full token metadata to all callers**: `sub`, `username`, and `email` are PII;
  scope the response fields to the minimum the calling resource server needs.

## Gotchas

- **Token type hint**: RFC 7662 allows `token_type_hint` (`access_token` / `refresh_token`);
  ignoring it adds one extra D1 query per mismatched hint — handle it to reduce latency.
- **Clock skew on `exp`**: Workers system time is accurate to seconds; add a small leeway
  (≤30 s) when evaluating `exp` to account for clock drift at resource servers.
- **KV eventual consistency**: a token revoked in one colo may still return `active: true` from
  another colo's KV read within the replication window; use KV with `cacheTtl: 0` for
  revocation-sensitive lookups.
- **D1 read replica lag**: D1 primary writes propagate to read replicas with latency; revocation
  writes should target the primary directly; consider a short post-revocation grace window.
- **RFC 7662 §2.2 `aud` field**: if the introspection endpoint serves multiple authorization
  servers, include `aud` restricted to the calling resource server to prevent response reuse.

## Verification

```bash
# 1. Unauthenticated request must return 401
curl -s -o /dev/null -w "%{http_code}" \
  -X POST https://auth.example.workers.dev/introspect \
  -d "token=abc123"
# expect: 401

# 2. Invalid token must return active: false (not 404)
curl -s -X POST https://auth.example.workers.dev/introspect \
  -H "Authorization: Basic $(echo -n 'resource-server:secret' | base64)" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=definitely-not-a-real-token"
# expect: {"active":false}

# 3. Valid token must include required fields
TOKEN=$(get_valid_test_token)
curl -s -X POST https://auth.example.workers.dev/introspect \
  -H "Authorization: Basic $(echo -n 'resource-server:secret' | base64)" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=$TOKEN" | jq 'has("scope") and has("exp") and .active == true'
# expect: true

# 4. Response must carry no-store cache header
curl -sI -X POST https://auth.example.workers.dev/introspect ... | grep -i cache-control
# expect: Cache-Control: no-store
```

## Related

- `cloudflare-access-jwt-assertion-validation.md`
- `jwt-refresh-token-rotation-durable-objects.md`
- `oauth-pkce-flow.md`
- `api-key-rotation-workers-kv-secrets.md`
- `timing-safe-compare.md`

## Sources

- https://www.rfc-editor.org/rfc/rfc7662 — OAuth 2.0 Token Introspection
- https://developers.cloudflare.com/d1/
- https://owasp.org/www-project-api-security/ — OWASP API Security Top 10
