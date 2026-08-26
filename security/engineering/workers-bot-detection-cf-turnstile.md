# Cloudflare Turnstile Bot Detection in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Workers endpoints are being hit by bots, scrapers, or credential-stuffing attacks. You want to integrate Cloudflare Turnstile so that client-side challenge tokens are verified server-side, each token is single-use, and per-IP abuse is tracked without slowing down legitimate traffic.

---

## Context
Turnstile is a CAPTCHA alternative that issues a `cf-turnstile-response` token from the browser. The Worker verifies the token with Cloudflare's `siteverify` API, then checks KV to ensure it has not been replayed. Per-IP counters in KV gate requests before token verification for cheap early rejection. Every challenge outcome is logged to D1 `bot_challenges` for audit and trend analysis.

---

## D1 Schema
```sql
CREATE TABLE IF NOT EXISTS bot_challenges (
  id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  ip            TEXT NOT NULL,
  token_hash    TEXT,
  outcome       TEXT NOT NULL CHECK(outcome IN ('pass','fail','replay','rate_limited')),
  hostname      TEXT,
  action        TEXT,
  error_codes   TEXT,
  created_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_bc_ip         ON bot_challenges(ip);
CREATE INDEX IF NOT EXISTS idx_bc_outcome    ON bot_challenges(outcome);
CREATE INDEX IF NOT EXISTS idx_bc_created_at ON bot_challenges(created_at);
```

---

## Turnstile Verification Helper
```typescript
// src/turnstile.ts
const SITEVERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify';

export interface TurnstileResult {
  success: boolean;
  hostname?: string;
  action?: string;
  cdata?: string;
  error_codes?: string[];
}

export async function verifyTurnstileToken(
  token: string,
  secretKey: string,
  remoteIp?: string
): Promise<TurnstileResult> {
  const body = new FormData();
  body.set('secret',   secretKey);
  body.set('response', token);
  if (remoteIp) body.set('remoteip', remoteIp);

  const resp = await fetch(SITEVERIFY_URL, { method: 'POST', body });
  if (!resp.ok) throw new Error(`Turnstile siteverify HTTP ${resp.status}`);

  const data = await resp.json<{
    success: boolean;
    hostname?: string;
    action?: string;
    cdata?: string;
    'error-codes'?: string[];
  }>();

  return {
    success:     data.success,
    hostname:    data.hostname,
    action:      data.action,
    cdata:       data.cdata,
    error_codes: data['error-codes'],
  };
}
```

---

## Worker: Rate Limiting + Replay Prevention + Audit
```typescript
// src/index.ts
import type { Env } from './env';
import { verifyTurnstileToken } from './turnstile';

const RATE_LIMIT_WINDOW = 60;    // seconds
const RATE_LIMIT_MAX   = 10;    // requests per window per IP
const TOKEN_TTL        = 300;   // 5 minutes: replay prevention window

async function hashToken(token: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}

async function checkRateLimit(ip: string, env: Env): Promise<boolean> {
  const key = `rl:${ip}`;
  const raw = await env.BOT_KV.get(key);
  const count = raw ? parseInt(raw, 10) : 0;
  if (count >= RATE_LIMIT_MAX) return false;

  // Increment; set TTL only on first request in window
  if (count === 0) {
    await env.BOT_KV.put(key, '1', { expirationTtl: RATE_LIMIT_WINDOW });
  } else {
    // Cannot refresh TTL on existing KV key; overwrite preserves TTL approximately
    await env.BOT_KV.put(key, String(count + 1), { expirationTtl: RATE_LIMIT_WINDOW });
  }
  return true;
}

async function isReplay(tokenHash: string, env: Env): Promise<boolean> {
  const existing = await env.BOT_KV.get(`ts:${tokenHash}`);
  return existing !== null;
}

async function markTokenUsed(tokenHash: string, env: Env): Promise<void> {
  await env.BOT_KV.put(`ts:${tokenHash}`, '1', { expirationTtl: TOKEN_TTL });
}

async function auditLog(
  env: Env,
  ip: string,
  outcome: string,
  tokenHash?: string,
  hostname?: string,
  action?: string,
  errorCodes?: string[]
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO bot_challenges (ip, token_hash, outcome, hostname, action, error_codes)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(
    ip,
    tokenHash ?? null,
    outcome,
    hostname ?? null,
    action ?? null,
    errorCodes ? JSON.stringify(errorCodes) : null
  ).run();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const ip = request.headers.get('CF-Connecting-IP') ?? '0.0.0.0';

    // 1. Per-IP rate limit (cheap, no D1)
    const allowed = await checkRateLimit(ip, env);
    if (!allowed) {
      await auditLog(env, ip, 'rate_limited');
      return new Response('Too Many Requests', { status: 429 });
    }

    // 2. Extract Turnstile token
    const body = await request.json<{ 'cf-turnstile-response'?: string }>().catch(() => ({}));
    const token = body['cf-turnstile-response'];
    if (!token) {
      return new Response('Missing Turnstile token', { status: 400 });
    }

    const tokenHash = await hashToken(token);

    // 3. Replay prevention
    if (await isReplay(tokenHash, env)) {
      await auditLog(env, ip, 'replay', tokenHash);
      return new Response('Token already used', { status: 400 });
    }

    // 4. Server-side Turnstile verification
    const result = await verifyTurnstileToken(token, env.TURNSTILE_SECRET_KEY, ip);

    if (!result.success) {
      await auditLog(env, ip, 'fail', tokenHash, result.hostname, result.action, result.error_codes);
      return new Response('Bot challenge failed', { status: 403 });
    }

    // 5. Mark token as used
    await markTokenUsed(tokenHash, env);
    await auditLog(env, ip, 'pass', tokenHash, result.hostname, result.action);

    // 6. Process the actual request
    return new Response(JSON.stringify({ ok: true }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## wrangler.toml
```toml
[vars]
TURNSTILE_SITE_KEY = "0x4AAAAAAA..."

[[kv_namespaces]]
binding = "BOT_KV"
id      = "<KV_NAMESPACE_ID>"

[[d1_databases]]
binding      = "DB"
database_name = "my-db"
database_id   = "<D1_DATABASE_ID>"
```

```bash
wrangler secret put TURNSTILE_SECRET_KEY
```

---

## Anti-patterns
- **Client-side-only Turnstile** — the token must be verified server-side; a client-side check is trivially bypassed.
- **Allowing token reuse** — Turnstile tokens are single-use by design; replaying one indicates a bot pipeline.
- **IP blocking without rate limiting** — hard blocks are easy to evade with IP rotation; rate limiting degrades abuse gracefully.
- **Logging raw Turnstile tokens** — hash them before storing to prevent any theoretical replay from logs.

---

## Gotchas
- Turnstile `siteverify` returns HTTP 200 even for failures; always inspect the `success` field in the JSON body.
- `CF-Connecting-IP` header is only trustworthy when the request goes through Cloudflare's proxy; never trust it from direct clients.
- KV writes are eventually consistent — a tiny race window exists for replay; acceptable for most use-cases.
- The `remoteip` parameter in siteverify is optional but recommended; it helps Cloudflare improve detection accuracy.

---

## Verification
```bash
# Apply schema
wrangler d1 execute my-db --file schema.sql

# Test with a dummy token (should fail siteverify)
curl -X POST https://<worker>.workers.dev/ \
  -H 'Content-Type: application/json' \
  -d '{"cf-turnstile-response":"XXXX.DUMMY.TOKEN.XXXX"}'
# Expect 403

# Query audit log
wrangler d1 execute my-db \
  --command "SELECT outcome, count(*) FROM bot_challenges GROUP BY outcome"

# Simulate rate limit
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<worker>.workers.dev/ \
    -H 'Content-Type: application/json' -d '{"cf-turnstile-response":"X"}'
done
# Last 2 requests should return 429
```

---

## Related
- `workers-jwt-refresh-token-rotation.md`
- `workers-api-key-rotation-kv-d1.md`

---

## Sources
- Cloudflare Turnstile Docs — https://developers.cloudflare.com/turnstile/
- Turnstile Server-side Validation — https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- Cloudflare KV Docs — https://developers.cloudflare.com/kv/
