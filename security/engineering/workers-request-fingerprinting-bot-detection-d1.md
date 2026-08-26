# Workers Request Fingerprinting and Bot Detection with D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Cloudflare Bot Management scores are unavailable on your plan, or you need supplementary
signals beyond the `cf.bot_management.score` field.  You want a Cloudflare Worker that:
- Builds a multi-dimensional fingerprint (TLS, HTTP/2 frame order, header order, JA3-
  equivalent) from each incoming request.
- Looks up the fingerprint hash in D1 to classify requests as known-good, known-bad, or
  unknown.
- Rate-limits unknowns and increments a score column when suspicious behaviour repeats.
- Exposes a management endpoint to seed or update the fingerprint database.

---

## Context

Browser and HTTP library clients differ in subtle, stable ways: header order, HTTP/2
SETTINGS frame values, TLS cipher suite ordering (the "JA3" fingerprint), and the
presence or absence of pseudo-headers.  Cloudflare exposes many of these via the `cf`
object on the `Request`.  By hashing a stable subset into a fingerprint you can:
- Allowlist known SDK user-agents that always produce the same fingerprint.
- Blocklist fingerprints associated with credential-stuffing toolkits.
- Surface anomalies where a human-looking user-agent ships a bot-library fingerprint.

D1 is the storage layer: a `fingerprints` table holds the hash, a human label, a
`disposition` (allow / block / challenge), and a running `hit_count`.

---

## 1. Extracting Fingerprint Signals

```typescript
// src/fingerprint.ts
export interface FingerprintSignals {
  httpVersion: string;       // '2' | '1.1'
  tlsCipher: string;         // e.g. 'AEAD-AES128-GCM-SHA256'
  tlsVersion: string;        // e.g. 'TLSv1.3'
  headerOrder: string;       // comma-joined header names in arrival order
  acceptLanguage: string;
  acceptEncoding: string;
  userAgentRaw: string;
  country: string;
}

export function extractSignals(req: Request): FingerprintSignals {
  const cf = (req as any).cf ?? {};

  // Header order — Workers preserves insertion order on the Headers object
  const headerOrder = [...req.headers.keys()].join(',');

  return {
    httpVersion: cf.httpProtocol ?? 'unknown',
    tlsCipher: cf.tlsCipher ?? 'unknown',
    tlsVersion: cf.tlsVersion ?? 'unknown',
    headerOrder,
    acceptLanguage: req.headers.get('accept-language') ?? '',
    acceptEncoding: req.headers.get('accept-encoding') ?? '',
    userAgentRaw: req.headers.get('user-agent') ?? '',
    country: cf.country ?? 'XX',
  };
}
```

---

## 2. Hashing the Fingerprint

```typescript
// src/fingerprint.ts (continued)
export async function hashFingerprint(
  signals: FingerprintSignals,
): Promise<string> {
  // Concatenate stable, order-sensitive fields
  const raw = [
    signals.httpVersion,
    signals.tlsVersion,
    signals.tlsCipher,
    signals.headerOrder,
    signals.acceptEncoding,
    signals.acceptLanguage,
    // Intentionally exclude userAgent — it is trivially spoofed.
    // Keep it in signals for logging, not in the hash.
  ].join('|');

  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(raw),
  );

  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
```

---

## 3. D1 Schema

```sql
CREATE TABLE IF NOT EXISTS fingerprints (
  hash        TEXT PRIMARY KEY,
  label       TEXT NOT NULL DEFAULT '',
  disposition TEXT NOT NULL DEFAULT 'unknown'
                   CHECK (disposition IN ('allow','block','challenge','unknown')),
  hit_count   INTEGER NOT NULL DEFAULT 0,
  first_seen  INTEGER NOT NULL,
  last_seen   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fp_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER NOT NULL,
  hash        TEXT    NOT NULL,
  ip_hash     TEXT    NOT NULL,   -- SHA-256 of the client IP, not raw IP
  path        TEXT    NOT NULL,
  disposition TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fp_events_hash ON fp_events (hash, ts);
CREATE INDEX IF NOT EXISTS idx_fp_events_ip   ON fp_events (ip_hash, ts);
```

---

## 4. D1 Lookup and Decision

```typescript
// src/classify.ts
export type Disposition = 'allow' | 'block' | 'challenge' | 'unknown';

export interface FpRow {
  hash: string;
  label: string;
  disposition: Disposition;
  hit_count: number;
}

export async function classify(
  db: D1Database,
  hash: string,
): Promise<Disposition> {
  const row = await db
    .prepare(`SELECT disposition, hit_count FROM fingerprints WHERE hash = ?`)
    .bind(hash)
    .first<FpRow>();

  if (!row) return 'unknown';
  return row.disposition;
}

export async function upsertFingerprint(
  db: D1Database,
  hash: string,
  disposition: Disposition,
): Promise<void> {
  const now = Date.now();
  await db
    .prepare(
      `INSERT INTO fingerprints (hash, disposition, hit_count, first_seen, last_seen)
         VALUES (?, ?, 1, ?, ?)
       ON CONFLICT(hash) DO UPDATE
         SET hit_count = hit_count + 1,
             disposition = excluded.disposition,
             last_seen = excluded.last_seen`,
    )
    .bind(hash, disposition, now, now)
    .run();
}
```

---

## 5. Worker Entry Point

```typescript
// src/index.ts
import { extractSignals, hashFingerprint } from './fingerprint';
import { classify, upsertFingerprint, Disposition } from './classify';

export interface Env {
  DB: D1Database;
  ADMIN_SECRET: string;
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Admin seed endpoint (POST /admin/fingerprints)
    if (req.method === 'POST' && new URL(req.url).pathname === '/admin/fingerprints') {
      return handleAdminSeed(req, env);
    }

    const signals = extractSignals(req);
    const hash = await hashFingerprint(signals);
    const disposition = await classify(env.DB, hash);

    // Log every request asynchronously — do not block the response
    const ipHash = await hashIp(req.headers.get('CF-Connecting-IP') ?? '');
    ctx.waitUntil(
      logEvent(env.DB, hash, ipHash, new URL(req.url).pathname, disposition),
    );

    if (disposition === 'block') {
      return new Response('Forbidden', { status: 403 });
    }

    if (disposition === 'unknown') {
      // Challenge: return 429 with Retry-After, let the client retry
      // Increment unknown count; after N hits auto-escalate to block
      ctx.waitUntil(upsertFingerprint(env.DB, hash, 'unknown'));
      const hitCount = await getHitCount(env.DB, hash);
      if (hitCount > 20) {
        ctx.waitUntil(upsertFingerprint(env.DB, hash, 'block'));
        return new Response('Forbidden — repeated unknown fingerprint', { status: 403 });
      }
      // Pass through for now but add a challenge header the frontend can read
      const resp = await fetch(req);
      const mutable = new Response(resp.body, resp);
      mutable.headers.set('X-Bot-Challenge', 'captcha');
      return mutable;
    }

    // allow — pass through
    return fetch(req);
  },
};

async function hashIp(ip: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(ip));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function logEvent(
  db: D1Database,
  hash: string,
  ipHash: string,
  path: string,
  disposition: string,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO fp_events (ts, hash, ip_hash, path, disposition) VALUES (?,?,?,?,?)`,
    )
    .bind(Date.now(), hash, ipHash, path, disposition)
    .run();
}

async function getHitCount(db: D1Database, hash: string): Promise<number> {
  const row = await db
    .prepare(`SELECT hit_count FROM fingerprints WHERE hash = ?`)
    .bind(hash)
    .first<{ hit_count: number }>();
  return row?.hit_count ?? 0;
}

async function handleAdminSeed(req: Request, env: Env): Promise<Response> {
  const authHeader = req.headers.get('Authorization') ?? '';
  const token = authHeader.replace('Bearer ', '');
  // Timing-safe compare
  const encoder = new TextEncoder();
  const a = encoder.encode(token);
  const b = encoder.encode(env.ADMIN_SECRET);
  if (a.length !== b.length) return new Response('Unauthorized', { status: 401 });
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  if (diff !== 0) return new Response('Unauthorized', { status: 401 });

  const body = await req.json<{ hash: string; label: string; disposition: string }>();
  if (!body.hash || !body.disposition) {
    return new Response('Bad Request', { status: 400 });
  }
  const db: D1Database = env.DB;
  await upsertFingerprint(db, body.hash, body.disposition as Disposition);
  return Response.json({ ok: true });
}
```

---

## 6. Seeding Known-Bad Fingerprints via CI

```bash
# Export JA3 hash from a known bot capture and seed it
curl -X POST https://bot-detector.<account>.workers.dev/admin/fingerprints \
  -H "Authorization: Bearer $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"hash":"<sha256>","label":"curl/7.68 default","disposition":"block"}'
```

---

## Anti-patterns

- **Using `User-Agent` in the hash** — trivially spoofed; use it for logging context
  only, never as the primary discriminator.
- **Storing raw client IPs in D1** — hash IPs (SHA-256 + a per-deployment HMAC key)
  before storing; raw IPs are PII in most jurisdictions.
- **Blocking on first unknown fingerprint** — new browsers and SDK versions produce new
  fingerprints legitimately; use a hit-count threshold or challenge-first strategy.
- **Running classify() synchronously on every request** — for high-traffic Workers,
  pre-warm an in-memory LRU cache of recent hashes to avoid D1 latency on every hop.
- **Exposing the admin seed endpoint without auth** — the endpoint lets an attacker
  allowlist their own fingerprint; protect it with a strong secret and consider IP-
  restricting it at the Cloudflare firewall level.

---

## Gotchas

- `req.headers.keys()` order in Workers matches the wire order for HTTP/1.1; for HTTP/2
  the order of pseudo-headers (`:method`, `:path`, etc.) is not exposed via the Headers
  API — use `cf.httpProtocol` to flag HTTP/2 requests separately.
- `cf.tlsCipher` is not populated for requests terminated at an upstream proxy before
  the Worker; validate it is non-empty before including in the hash.
- D1 is eventually consistent within a region; if you run a multi-region Worker, a
  fingerprint seeded in one region may take up to a few seconds to propagate.
- The auto-escalation from `unknown` → `block` happens inside `waitUntil`; a burst of
  concurrent requests for the same hash may all reach the threshold check simultaneously
  before any one write commits — add a `hit_count > threshold` guard in the DB query
  rather than in application logic alone.

---

## Verification

```bash
# Confirm unknown fingerprint returns pass-through with challenge header
curl -I https://bot-detector.<account>.workers.dev/

# Confirm blocked fingerprint returns 403
curl -I -H "user-agent: BlockedBot/1.0" https://bot-detector.<account>.workers.dev/
# (after seeding that UA's fingerprint as blocked)

# Check event log
wrangler d1 execute bot-detection \
  --command "SELECT disposition, COUNT(*) FROM fp_events GROUP BY disposition"
```

---

## Related

- `cloudflare-bot-management-abuse-prevention.md`
- `rate-limiting-per-user-d1-durable-objects.md`
- `ato-behavioral-anomaly-scoring-d1.md`
- `timing-safe-compare.md`

---

## Sources

- Cloudflare `cf` request object: https://developers.cloudflare.com/workers/runtime-apis/request/#the-cf-property-requestinitcfproperties
- JA3 fingerprinting: https://github.com/salesforce/ja3
- RFC 9110 HTTP Semantics (header field ordering): https://www.rfc-editor.org/rfc/rfc9110
- D1 documentation: https://developers.cloudflare.com/d1/
