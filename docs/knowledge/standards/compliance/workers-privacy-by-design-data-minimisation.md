# Privacy-by-Design Data Minimisation Patterns in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers API inadvertently leaks PII fields (raw IPs, email addresses, full names) in responses or stores more personal data than each endpoint requires. You need request scrubbing middleware that strips unnecessary PII before it reaches your business logic, D1 schema conventions that prevent raw PII storage, and a SELECT column allowlist pattern that blocks accidental PII exposure in API responses.

---

## Context

Privacy-by-design (GDPR Art. 25, LGPD Art. 46, PDPA §37) requires that data minimisation be an architectural default, not an afterthought. In a Workers context this means: (1) stripping PII fields from incoming requests as early as possible in the middleware chain, before they are logged or forwarded; (2) designing D1 tables so that raw identifiers like email addresses and IP addresses are never stored — only hashed or tokenised references and a separate `pii_vault` table holds sensitive fields under stricter access control; and (3) constructing SELECT queries from an explicit column allowlist so that adding a new PII column to a table does not automatically expose it in API responses. Together these three patterns implement data minimisation at the transport, storage, and retrieval layers.

---

## Section 1 — D1 Schema Conventions

```sql
-- users: core identity table — no raw email, no raw IP
CREATE TABLE IF NOT EXISTS users (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  id_hash         TEXT NOT NULL UNIQUE,   -- SHA-256 of canonical identifier
  display_name    TEXT,                   -- non-identifying, user-chosen
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
  -- NO: email TEXT, ip_address TEXT, full_name TEXT
);

-- pii_vault: sensitive fields stored separately with their own access control
-- Only backend processes with explicit permission query this table.
CREATE TABLE IF NOT EXISTS pii_vault (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  field_name      TEXT NOT NULL,    -- e.g. 'email', 'phone', 'full_name'
  field_value     TEXT NOT NULL,    -- ideally encrypted at application layer
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(user_id, field_name)
);

CREATE INDEX IF NOT EXISTS idx_pii_vault_user ON pii_vault(user_id);

-- analytics_events: no user-linkable fields in the events table
CREATE TABLE IF NOT EXISTS analytics_events (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  session_token   TEXT NOT NULL,   -- rotating pseudonymous session token
  event_name      TEXT NOT NULL,
  event_time      TEXT NOT NULL DEFAULT (datetime('now')),
  properties      TEXT,            -- JSON blob — PII fields scrubbed before insert
  country_code    TEXT,            -- 2-letter, not full IP
  device_type     TEXT             -- 'mobile'|'desktop'|'tablet', not UA string
  -- NO: ip_address, user_agent, email, user_id linkable to pii_vault
);

CREATE INDEX IF NOT EXISTS idx_analytics_session ON analytics_events(session_token);
CREATE INDEX IF NOT EXISTS idx_analytics_time    ON analytics_events(event_time);
```

---

## Section 2 — Request Scrubbing Middleware

```typescript
import { Hono, MiddlewareHandler } from 'hono';
import { createHash } from 'node:crypto';

export interface Env {
  DB: D1Database;
}

// PII fields that must never flow past the scrubber into business logic
const PII_FIELDS_BLACKLIST = new Set([
  'email',
  'phone',
  'full_name',
  'first_name',
  'last_name',
  'ip_address',
  'ssn',
  'tax_id',
  'credit_card',
  'iban',
  'passport_number',
  'date_of_birth',
]);

// Per-endpoint allowlist of fields permitted to pass through
const ENDPOINT_FIELD_ALLOWLIST: Record<string, Set<string>> = {
  '/api/analytics': new Set(['session_token', 'event_name', 'properties', 'device_type']),
  '/api/profile':   new Set(['display_name', 'updated_at']),
  '/api/search':    new Set(['query', 'filters', 'page', 'limit']),
};

function sha256(value: string): string {
  return createHash('sha256').update(value).digest('hex');
}

/**
 * piiScrubber: strips PII fields from JSON request bodies and replaces raw IP
 * with its SHA-256 hash in the request context before any handler sees the data.
 */
export const piiScrubber: MiddlewareHandler<{ Bindings: Env }> = async (
  c,
  next
) => {
  const contentType = c.req.header('Content-Type') ?? '';
  const path = new URL(c.req.url).pathname;

  if (contentType.includes('application/json')) {
    const rawBody = await c.req.text();
    let body: Record<string, unknown>;

    try {
      body = JSON.parse(rawBody);
    } catch {
      return c.json({ error: 'Invalid JSON' }, 400);
    }

    const allowed = ENDPOINT_FIELD_ALLOWLIST[path];

    // Remove fields that are in the PII blacklist OR not in the endpoint allowlist
    for (const key of Object.keys(body)) {
      if (PII_FIELDS_BLACKLIST.has(key) || (allowed && !allowed.has(key))) {
        delete body[key];
      }
    }

    // Hash any remaining identifier-like values if they slipped through
    if (typeof body['identifier'] === 'string') {
      body['identifier_hash'] = sha256(body['identifier'] as string);
      delete body['identifier'];
    }

    // Replace raw IP with hash in headers context
    const rawIp = c.req.header('CF-Connecting-IP') ?? '';
    c.set('ip_hash' as never, rawIp ? sha256(rawIp) : null);
    c.set('scrubbed_body' as never, body);
  }

  // Strip X-Forwarded-For and similar headers before forwarding downstream
  // (handled automatically by Cloudflare; logged here for awareness)

  return next();
};

const app = new Hono<{ Bindings: Env }>();
app.use('*', piiScrubber);

// POST /api/analytics — store a scrubbed analytics event
app.post('/api/analytics', async (c) => {
  const body = c.get('scrubbed_body' as never) as Record<string, unknown>;
  const ipHash = c.get('ip_hash' as never) as string | null;

  // Derive country from CF header (2-letter, not IP)
  const countryCode = c.req.header('CF-IPCountry') ?? null;

  // Classify device type without storing user-agent string
  const ua = c.req.header('User-Agent') ?? '';
  const deviceType = /Mobile|Android|iPhone/i.test(ua)
    ? 'mobile'
    : /Tablet|iPad/i.test(ua)
    ? 'tablet'
    : 'desktop';

  await c.env.DB.prepare(
    `INSERT INTO analytics_events
       (session_token, event_name, properties, country_code, device_type)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(
    (body['session_token'] as string) ?? 'unknown',
    (body['event_name'] as string) ?? 'unknown',
    body['properties'] ? JSON.stringify(body['properties']) : null,
    countryCode,
    deviceType
  ).run();

  return c.json({ status: 'recorded' }, 201);
});

export default app;
```

---

## Section 3 — SELECT Column Allowlist Pattern

```typescript
import type { D1Database } from '@cloudflare/workers-types';

/**
 * SafeSelectBuilder: constructs SELECT queries from an explicit column allowlist.
 * Adding a column to the D1 table does NOT expose it in API responses unless
 * the developer explicitly adds it to ALLOWED_COLUMNS for that table.
 */
const ALLOWED_COLUMNS: Record<string, Set<string>> = {
  users: new Set(['id', 'display_name', 'created_at', 'updated_at']),
  analytics_events: new Set([
    'id', 'session_token', 'event_name', 'event_time',
    'properties', 'country_code', 'device_type',
  ]),
  // pii_vault is intentionally NOT listed — it is never selected by the API layer
};

export async function safeSelect(
  db: D1Database,
  table: string,
  requestedColumns: string[],
  whereClause: string,
  bindings: unknown[]
): Promise<Record<string, unknown>[]> {
  const allowed = ALLOWED_COLUMNS[table];
  if (!allowed) {
    throw new Error(`Table '${table}' is not in the safe-select allowlist`);
  }

  // Filter to only the intersection of requested and allowed columns
  const safeColumns = requestedColumns.filter((col) => allowed.has(col));
  if (safeColumns.length === 0) {
    throw new Error('No permitted columns in requested set');
  }

  // Both table name and column names are validated against compile-time sets
  const sql = `SELECT ${safeColumns.join(', ')} FROM ${table} WHERE ${whereClause}`;
  const { results } = await db.prepare(sql).bind(...bindings).all();
  return results as Record<string, unknown>[];
}

// Usage example in a GET /users/:id handler:
//
// app.get('/users/:id', async (c) => {
//   const rows = await safeSelect(
//     c.env.DB,
//     'users',
//     ['id', 'display_name', 'created_at', 'email'],  // 'email' will be stripped
//     'id = ?',
//     [c.req.param('id')]
//   );
//   return rows.length ? c.json(rows[0]) : c.json({ error: 'Not found' }, 404);
// });

/**
 * piiVaultWrite: the ONLY function permitted to write to pii_vault.
 * Call it explicitly for PII fields; never fall through from a generic insert.
 */
export async function piiVaultWrite(
  db: D1Database,
  userId: string,
  fields: Record<string, string>  // { email: 'user@example.com', phone: '+66...' }
): Promise<void> {
  const stmt = db.prepare(
    `INSERT INTO pii_vault (user_id, field_name, field_value)
     VALUES (?, ?, ?)
     ON CONFLICT(user_id, field_name) DO UPDATE SET field_value = excluded.field_value`
  );

  const stmts = Object.entries(fields).map(([field, value]) =>
    stmt.bind(userId, field, value)
  );

  await db.batch(stmts);
}

/**
 * piiVaultRead: reads one field from pii_vault for a specific user.
 * Returns null if the field does not exist. Logs every access.
 */
export async function piiVaultRead(
  db: D1Database,
  userId: string,
  fieldName: string,
  accessReason: string
): Promise<string | null> {
  console.log(
    `[PII] Access to '${fieldName}' for user ${userId.slice(0, 8)}... ` +
    `Reason: ${accessReason}`
  );

  const row = await db
    .prepare(
      `SELECT field_value FROM pii_vault WHERE user_id = ? AND field_name = ?`
    )
    .bind(userId, fieldName)
    .first<{ field_value: string }>();

  return row?.field_value ?? null;
}
```

---

## Anti-patterns

- **Using `SELECT *` in any endpoint-facing query** — A `SELECT *` will automatically include any PII column added to the schema in the future; always name columns explicitly or use `safeSelect`.
- **Logging the full request body before scrubbing** — If your middleware logs the raw body for debugging, PII is captured in log storage before the scrubber runs. Log only after scrubbing, or log structural metadata (path, method, timestamp) only.
- **Storing the raw User-Agent string** — The UA string can be used to fingerprint individuals. Classify it to `mobile`/`tablet`/`desktop` at ingestion and discard the raw value.
- **Putting PII in URL query parameters** — Query parameters appear in CF Access logs, browser history, and Referer headers. Route PII through POST bodies and scrub them there.
- **Treating `id_hash` as pseudonymous if the input space is small** — If `identifier` is a phone number or a short username, SHA-256 is reversible by brute force. Use HMAC-SHA256 with a secret key stored in Workers Secrets.

---

## Gotchas

- `pii_vault` must be excluded from the retention policy engine's allowlist (`TABLE_ALLOWLIST` in `workers-data-retention-policy-engine.md`) — PII vault records need their own, separately governed retention rules.
- Cloudflare logs (Logpush) may capture request headers and URLs even when your Worker does not; configure Logpush field exclusions for `X-Subject-ID` and similar headers.
- The `CF-IPCountry` header returns `XX` for unknown country and `T1` for Tor exit nodes; handle these values explicitly rather than storing them as valid country codes.
- Workers `crypto.subtle.digest` is the Web Crypto API alternative to Node's `createHash`; use it for better Workers compatibility: `const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)))].map(b => b.toString(16).padStart(2,'0')).join('')`.

---

## Verification

```bash
# Apply schema
wrangler d1 execute privacy-db --file=schema.sql

# Post an analytics event with PII fields — they should be stripped
curl -X POST https://your-worker.dev/api/analytics \
  -H 'Content-Type: application/json' \
  -d '{"session_token":"tok_abc123","event_name":"page_view",\
       "email":"user@example.com","ip_address":"1.2.3.4"}'

# Verify no PII stored in analytics_events
wrangler d1 execute privacy-db \
  --command "SELECT * FROM analytics_events ORDER BY event_time DESC LIMIT 5;"

# Check pii_vault is empty (no accidental writes)
wrangler d1 execute privacy-db \
  --command "SELECT COUNT(*) FROM pii_vault;"

# Test safeSelect strips 'email' column request
# (invoke via integration test or curl against a test endpoint)
curl 'https://your-worker.dev/users/<user-id>?fields=id,display_name,email'
# Response must NOT contain 'email'
```

---

## Related

- `brazil-lgpd-workers-d1-consent.md`
- `thailand-pdpa-workers-d1.md`
- `nigeria-ndpr-workers-d1.md`
- `workers-data-retention-policy-engine.md`

---

## Sources

- GDPR Art. 25 — Data protection by design and by default — https://gdpr-info.eu/art-25-gdpr/
- Cloudflare Workers Crypto API — https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- OWASP Data Minimization Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Abuse_Case_Cheat_Sheet.html
