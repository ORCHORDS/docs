# OAuth2 Client Credentials Flow in Cloudflare Workers with D1 Token Caching

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker calls a downstream API that requires an OAuth2 bearer token. Fetching a new token on every request adds 100–500 ms of latency and counts against rate limits on the token endpoint. You need a D1-backed cache so the Worker reuses valid tokens and only re-fetches when they expire.

## Context

OAuth2 client credentials (`grant_type=client_credentials`) is the machine-to-machine flow: no user consent step, just a `POST` with `client_id` + `client_secret` in exchange for an `access_token` and `expires_in`. D1 provides a durable, low-latency SQL store accessible from every Worker isolate in the same account, making it a natural token cache that survives across requests and isolate restarts.

---

## D1 Schema and Token Cache Helper

```typescript
// schema.sql — run once with wrangler d1 execute
// CREATE TABLE oauth_tokens (
//   client_id   TEXT PRIMARY KEY,
//   token       TEXT NOT NULL,
//   expires_at  INTEGER NOT NULL   -- Unix seconds
// );

// lib/token-cache.ts

export interface TokenRow {
  client_id: string;
  token: string;
  expires_at: number;
}

export interface OAuthConfig {
  tokenUrl: string;
  clientId: string;
  clientSecret: string;
  scope?: string;
}

const LEEWAY_SECONDS = 60; // Refresh 60 s before actual expiry

/**
 * Return a valid access token for the given client, using D1 as a cache.
 * Calls the token endpoint only when the cached token is absent or near-expired.
 */
export async function getOrRefreshToken(
  db: D1Database,
  config: OAuthConfig,
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);

  const row = await db
    .prepare('SELECT token, expires_at FROM oauth_tokens WHERE client_id = ?')
    .bind(config.clientId)
    .first<{ token: string; expires_at: number }>();

  if (row && row.expires_at - LEEWAY_SECONDS > now) {
    return row.token; // Cache hit — token still valid
  }

  // Cache miss or near-expiry: fetch a new token
  const token = await fetchClientCredentialsToken(config);

  // Upsert into D1
  await db
    .prepare(`
      INSERT INTO oauth_tokens (client_id, token, expires_at)
      VALUES (?, ?, ?)
      ON CONFLICT(client_id) DO UPDATE SET token = excluded.token, expires_at = excluded.expires_at
    `)
    .bind(config.clientId, token.access_token, now + token.expires_in)
    .run();

  return token.access_token;
}

interface TokenResponse {
  access_token: string;
  expires_in: number;
  token_type: string;
}

async function fetchClientCredentialsToken(config: OAuthConfig): Promise<TokenResponse> {
  const body = new URLSearchParams({
    grant_type: 'client_credentials',
    client_id: config.clientId,
    client_secret: <redacted-secret>
    ...(config.scope ? { scope: config.scope } : {}),
  });

  const res = await fetch(config.tokenUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!res.ok) {
    throw new Error(`Token endpoint returned ${res.status}: ${await res.text()}`);
  }
  return res.json<TokenResponse>();
}
```

---

## Worker Entry Point with 401 Retry

```typescript
// worker/index.ts
import { getOrRefreshToken, OAuthConfig } from '../lib/token-cache';

interface Env {
  DB: D1Database;
  OAUTH_TOKEN_URL: string;
  OAUTH_CLIENT_ID: string;
  OAUTH_CLIENT_SECRET: string;  // wrangler secret
  DOWNSTREAM_API: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const config: OAuthConfig = {
      tokenUrl: env.OAUTH_TOKEN_URL,
      clientId: env.OAUTH_CLIENT_ID,
      clientSecret: env.OAUTH_CLIENT_SECRET,
      scope: 'read:data write:data',
    };

    let token = await getOrRefreshToken(env.DB, config);
    let response = await callDownstream(env.DOWNSTREAM_API, token);

    // The upstream server may invalidate a token early (e.g. rolling secret).
    // On 401, force-evict the cache and retry once.
    if (response.status === 401) {
      await env.DB
        .prepare('DELETE FROM oauth_tokens WHERE client_id = ?')
        .bind(config.clientId)
        .run();
      token = await getOrRefreshToken(env.DB, config);
      response = await callDownstream(env.DOWNSTREAM_API, token);
    }

    return response;
  },
};

async function callDownstream(apiBase: string, token: string): Promise<Response> {
  return fetch(`${apiBase}/protected/resource`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}
```

---

## Scoped Tokens Per Downstream Service

When the Worker calls multiple downstream services, store one row per `client_id` (or per `client_id + scope` composite key):

```typescript
// Use a composite cache key when the same client_id needs different scopes
const cacheKey = `${config.clientId}::${config.scope ?? ''}`;
// Replace `client_id` column usage with this composite key in the SQL above.
```

Alternatively, maintain separate `OAuthConfig` objects with distinct `clientId` values corresponding to different service accounts.

---

## D1 Schema Migration for Scope-aware Caching

```sql
-- migration_001_add_scope.sql
ALTER TABLE oauth_tokens ADD COLUMN scope TEXT NOT NULL DEFAULT '';
-- Drop old primary key constraint and recreate
CREATE UNIQUE INDEX IF NOT EXISTS uq_client_scope ON oauth_tokens(client_id, scope);
```

---

## Anti-patterns

- **Caching tokens in a Worker global variable** — globals are isolate-local and do not survive restarts or cross-isolate; D1 ensures durability.
- **Not applying the 60-second leeway** — tokens fetched at the last second may expire in-flight before the downstream API accepts them.
- **Logging the raw `access_token`** — tokens are credentials; treat them like passwords.
- **Storing `client_secret` in `wrangler.toml`** — commit it as a `wrangler secret` so it never appears in source control.

## Gotchas

- D1 is eventually consistent across regions; in a race between two cold-start isolates, two token fetches may occur simultaneously. The `ON CONFLICT ... DO UPDATE` upsert is idempotent so both writes succeed harmlessly.
- `expires_in` from the token endpoint is in seconds relative to the time of the response, not absolute epoch time — always add it to `Date.now() / 1000` at response time.
- D1 `first()` returns `null` (not `undefined`) when no row matches; check for `null` explicitly.

## Verification

```bash
# Check token cache contents via wrangler
wrangler d1 execute example project-db --command "SELECT client_id, expires_at FROM oauth_tokens;"

# Confirm cache hit: second request should complete faster (no token endpoint call)
time curl https://my-worker.workers.dev/protected
time curl https://my-worker.workers.dev/protected
```

## Related

- `workers-request-signing-hmac-sha256-verification.md`
- `cloudflare-zero-trust-api-gateway-workers.md`
- D1 documentation — `wrangler d1 execute`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.rfc-editor.org/rfc/rfc6749#section-4.4
- https://developers.cloudflare.com/workers/runtime-apis/bindings/d1/
