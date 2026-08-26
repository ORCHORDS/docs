# Workers Analytics Engine for Real-Time Security Telemetry

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your anonymous social platform has rate-limiting and JWT validation, but when an incident occurs you have no
fast, queryable stream of security events. CloudWatch-style logging adds cold-start latency; D1 writes
under attack load cause lock contention. You need sub-millisecond, non-blocking security event emission
with SQL-queryable aggregation and a pathway to automated response.

---

## Context

Cloudflare Analytics Engine (AE) is a write-path-optimized time-series store built into the Workers
runtime. `writeDataPoint()` is a fire-and-forget call that does not block the request path. Data is
queryable via the Analytics Engine SQL API within seconds. Unlike Logpush (raw log export) or D1
(transactional store), AE is designed for high-cardinality security telemetry: auth failures, rate-limit
hits, anomalous payloads, bot signals, and geographic anomalies.

For an anonymous platform where user identity is ephemeral, AE lets you correlate events by
hashed IP, device fingerprint, or anonymous session token without storing PII in a queryable table.

---

## 1. Defining a Security Event Schema

Analytics Engine rows have a fixed shape: up to 20 `blobs` (strings, max 1 KB each), 20 `doubles`
(float64), and 1 `index` string (used as the primary partition key, up to 32 bytes). Design a schema
that covers your top security event types without leaking PII.

```typescript
// src/telemetry/schema.ts
export const EVENT_TYPES = {
  AUTH_FAILURE:         'auth_fail',
  RATE_LIMIT_HIT:       'rate_limit',
  JWT_INVALID:          'jwt_invalid',
  JWT_EXPIRED:          'jwt_expired',
  ANOMALOUS_UA:         'anomalous_ua',
  CONTENT_MODERATION:   'content_mod',
  GEO_BLOCK:            'geo_block',
  VERSION_DOWNGRADE:    'ver_downgrade',
  HONEYPOT_HIT:         'honeypot',
  SQLI_ATTEMPT:         'sqli',
} as const;

export type EventType = typeof EVENT_TYPES[keyof typeof EVENT_TYPES];

export interface SecurityDataPoint {
  // index  — partition key, 32 bytes max
  index: string;       // e.g. "auth_fail"

  // blobs — descriptive, non-numeric fields
  eventType: EventType;
  hashedIp: string;    // SHA-256 hex of cf-connecting-ip, first 16 chars
  country: string;
  asn: string;
  path: string;        // URL path, truncated at 128 chars
  method: string;
  errorCode: string;
  sessionToken: string; // hashed anonymous session, NOT raw token
  userAgent: string;    // truncated, or 'redacted' if oversized

  // doubles — numeric / boolean fields
  timestampMs: number;
  statusCode: number;
  requestSizeBytes: number;
  isBotScore: number;   // Cloudflare Bot Management score (0-99), -1 if absent
}
```

---

## 2. The Telemetry Emitter

Wrap `writeDataPoint()` in a typed emitter that hashes PII at the call site so no raw identifiers
reach the analytics store.

```typescript
// src/telemetry/emitter.ts
import { SecurityDataPoint } from './schema';

async function sha256Hex(value: string): Promise<string> {
  const enc = new TextEncoder();
  const buf = await crypto.subtle.digest('SHA-256', enc.encode(value));
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 16); // 16 hex chars = 64-bit collision resistance, enough for grouping
}

export async function emitSecurityEvent(
  env: Env,
  request: Request,
  partial: Pick<SecurityDataPoint, 'eventType' | 'errorCode' | 'sessionToken'>
): Promise<void> {
  const ip = request.headers.get('cf-connecting-ip') ?? '0.0.0.0';
  const cf = request.cf ?? {};
  const url = new URL(request.url);

  const hashedIp = await sha256Hex(ip);
  const hashedSession = partial.sessionToken
    ? await sha256Hex(partial.sessionToken)
    : 'anonymous';

  const ua = (request.headers.get('user-agent') ?? '').slice(0, 200);

  env.SECURITY_ANALYTICS.writeDataPoint({
    indexes: [partial.eventType], // partition key
    blobs: [
      partial.eventType,
      hashedIp,
      (cf.country as string) ?? 'XX',
      String(cf.asn ?? ''),
      url.pathname.slice(0, 128),
      request.method,
      partial.errorCode,
      hashedSession,
      ua,
    ],
    doubles: [
      Date.now(),
      0,        // statusCode — filled by response wrapper
      Number(request.headers.get('content-length') ?? 0),
      Number((cf as Record<string, unknown>).botManagementScore ?? -1),
    ],
  });
}
```

Bind `SECURITY_ANALYTICS` in `wrangler.toml`:

```toml
[[analytics_engine_datasets]]
binding = "SECURITY_ANALYTICS"
dataset = "security_events"
```

---

## 3. Middleware Integration

Integrate telemetry into your Worker's middleware pipeline without blocking the response.

```typescript
// src/middleware/security-telemetry.ts
import { emitSecurityEvent } from '../telemetry/emitter';

export function withSecurityTelemetry(
  handler: (req: Request, env: Env, ctx: ExecutionContext) => Promise<Response>
) {
  return async (
    request: Request,
    env: Env,
    ctx: ExecutionContext
  ): Promise<Response> => {
    let response: Response;
    try {
      response = await handler(request, env, ctx);
    } catch (err) {
      if (err instanceof Response) {
        response = err;
      } else {
        response = new Response('Internal Error', { status: 500 });
      }
    }

    // Emit after response is formed — non-blocking via ctx.waitUntil
    if (response.status === 401 || response.status === 403) {
      ctx.waitUntil(
        emitSecurityEvent(env, request, {
          eventType: response.status === 401 ? 'auth_fail' : 'jwt_invalid',
          errorCode: String(response.status),
          sessionToken: request.headers.get('x-session-token') ?? '',
        })
      );
    }

    return response;
  };
}
```

Using `ctx.waitUntil()` ensures the analytics write completes after the response is returned, adding
zero latency to the hot path.

---

## 4. Querying Security Events via the SQL API

The Analytics Engine SQL API is available at `https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`.

```typescript
// src/admin/security-query.ts
export async function queryAuthFailures(
  accountId: string,
  apiToken: string,
  windowMinutes = 5
): Promise<unknown[]> {
  const sql = `
    SELECT
      blob2 AS hashed_ip,
      blob3 AS country,
      count() AS failures,
      max(double1) AS last_seen_ms
    FROM security_events
    WHERE
      index1 = 'auth_fail'
      AND timestamp > now() - INTERVAL '${windowMinutes}' MINUTE
    GROUP BY hashed_ip, country
    HAVING failures > 10
    ORDER BY failures DESC
    LIMIT 100
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  if (!resp.ok) throw new Error(`AE query failed: ${resp.status}`);
  const data = (await resp.json()) as { data: unknown[] };
  return data.data;
}
```

---

## 5. Automated Response: Blocking Repeat Offenders

Combine AE query results with the Cloudflare Firewall API to auto-block IPs that exceed a threshold.
Run this in a scheduled Worker (cron trigger) rather than on the hot path.

```typescript
// src/scheduled/auto-block.ts
export async function autoBlockAbusers(env: Env): Promise<void> {
  const results = await queryAuthFailures(
    env.ACCOUNT_ID,
    env.CF_API_TOKEN,
    5 // last 5 minutes
  ) as Array<{ hashed_ip: string; failures: number }>;

  // AE stores hashed IPs — we need the raw IP to block.
  // Use a companion D1 table that maps hashed_ip → raw_ip with a 15-min TTL
  // (see section 6 below). Only block if raw IP is available.
  for (const row of results) {
    if (row.failures < 50) continue;

    const rawIp = await env.DB.prepare(
      'SELECT raw_ip FROM ip_hash_index WHERE hashed_ip = ? AND expires_at > CURRENT_TIMESTAMP'
    )
      .bind(row.hashed_ip)
      .first<{ raw_ip: string }>();

    if (!rawIp) continue;

    await blockIpViaFirewall(env, rawIp.raw_ip, `auto-block: ${row.failures} auth failures in 5m`);
  }
}

async function blockIpViaFirewall(
  env: Env,
  ip: string,
  reason: string
): Promise<void> {
  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.ACCOUNT_ID}/firewall/access-rules/rules`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        mode: 'block',
        configuration: { target: 'ip', value: ip },
        notes: reason,
      }),
    }
  );
}
```

---

## 6. Short-lived IP Hash Index in D1

To connect AE's hashed IPs back to actionable raw IPs without logging IP addresses indefinitely:

```sql
-- Migration
CREATE TABLE ip_hash_index (
  hashed_ip  TEXT PRIMARY KEY,
  raw_ip     TEXT NOT NULL,
  expires_at TEXT NOT NULL  -- ISO8601, 15 min TTL
);

CREATE INDEX idx_ip_hash_expires ON ip_hash_index(expires_at);
```

```typescript
// Write on every request — upsert with 15-min expiry
export async function upsertIpHashIndex(
  env: Env,
  hashedIp: string,
  rawIp: string
): Promise<void> {
  const expiresAt = new Date(Date.now() + 15 * 60 * 1000).toISOString();
  await env.DB.prepare(
    `INSERT INTO ip_hash_index (hashed_ip, raw_ip, expires_at)
     VALUES (?, ?, ?)
     ON CONFLICT (hashed_ip) DO UPDATE SET raw_ip = excluded.raw_ip, expires_at = excluded.expires_at`
  )
    .bind(hashedIp, rawIp, expiresAt)
    .run();
}
```

Purge expired rows via a daily scheduled Worker to keep the table small.

---

## Anti-patterns

- **Writing raw IPs or session tokens into AE blobs** — AE data is retained for 90 days and queryable by
  any account member with Analytics access. Always hash PII before writing.
- **Calling `writeDataPoint()` inside `await`** — it is synchronous and returns `undefined`. Awaiting it
  is a no-op that may confuse readers into thinking it can throw.
- **Using AE as the sole audit trail** — AE is eventually consistent and has a ~seconds ingestion delay.
  For compliance audit logs use `workers-audit-log-immutable-r2-worm-pattern.md`.
- **One dataset for all event types** — high-volume events (rate limit hits) drown low-volume critical
  events (honeypot hits) in the same dataset. Use separate datasets or rely on `index1` filtering.
- **Blocking based on AE data alone without a D1 confirmation step** — AE aggregations can include
  hash collisions. Always confirm the raw IP via a secondary short-TTL index before automating blocks.

---

## Gotchas

- AE `writeDataPoint()` is lost if the Worker isolate is evicted before the write is flushed. For critical
  events, pair AE with a `ctx.waitUntil()` Tail Worker write to R2 as a durable fallback.
- AE SQL column names for blobs are `blob1`…`blob20` and doubles are `double1`…`double20` — there is no
  named-column support. Document your schema carefully and pin column positions.
- The AE SQL API rate limit is 1,200 requests/hour per account. Cache scheduled-query results in KV.
- `index1` must be ≤32 bytes. Event types longer than 32 characters are silently truncated.
- AE does not support `JOIN` — cross-reference queries must be done by fetching two result sets and
  merging in application code.

---

## Verification

```bash
# 1. Emit a test event via wrangler dev
# 2. Query via curl
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT index1, count() AS n FROM security_events WHERE timestamp > now() - INTERVAL '\''5'\'' MINUTE GROUP BY index1"}'

# 3. Confirm no raw IPs in blobs (all should be 16-char hex strings)
# Look at blob2 column in the results — verify format matches /^[0-9a-f]{16}$/
```

---

## Related

- `workers-audit-log-immutable-r2-worm-pattern.md`
- `workers-tail-workers-security-event-streaming.md`
- `rate-limiting-per-user-d1-durable-objects.md`
- `honeypot-tokens-canary.md`
- `cloudflare-rate-limiting-v2-api-abuse-prevention.md`

---

## Sources

- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Analytics Engine SQL API reference — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare Firewall Access Rules API — https://developers.cloudflare.com/firewall/api/cf-firewall-rules/
- Workers `ctx.waitUntil()` — https://developers.cloudflare.com/workers/runtime-apis/context/
- OWASP Logging Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
