# GDPR Article 20 Data Portability Export in Cloudflare Workers with R2

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Users exercise their GDPR Article 20 right to receive a machine-readable export of their personal data. The Worker collects rows from multiple D1 tables, lists the user's R2 uploads, assembles a structured JSON archive, compresses it with `CompressionStream`, uploads it to R2 with a 7-day TTL presigned URL, emails the download link via MailChannels, and records the export request in a D1 audit table.

---

## Context

GDPR Article 20 requires that personal data be provided in a structured, commonly used, and machine-readable format. Workers can orchestrate this across D1 and R2 in a single request handler because Cloudflare's 30-second CPU limit (Paid plan) is sufficient for most user datasets. For very large accounts a Durable Object or Queue-based background job should be used. Compression via the Web Streams `CompressionStream` API reduces R2 storage and transfer costs while staying within Worker memory limits. Presigned R2 URLs expire after 7 days, limiting exposure of the download link.

---

## Section 1 — D1 Schema

```sql
-- Tracks portability export requests
CREATE TABLE IF NOT EXISTS portability_requests (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id         TEXT NOT NULL,
  requested_at    INTEGER NOT NULL,
  completed_at    INTEGER,
  r2_key          TEXT,
  presigned_url   TEXT,
  url_expires_at  INTEGER,   -- Unix epoch ms, 7 days from completion
  status          TEXT NOT NULL DEFAULT 'pending',  -- pending | building | complete | failed
  email_sent      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_pr_user   ON portability_requests(user_id, requested_at);
CREATE INDEX IF NOT EXISTS idx_pr_status ON portability_requests(status);

-- Rate-limit table: 1 export per user per 24 hours
CREATE TABLE IF NOT EXISTS portability_rate_limit (
  user_id     TEXT PRIMARY KEY,
  last_request_at INTEGER NOT NULL
);
```

---

## Section 2 — Worker Implementation

```typescript
interface Env {
  DB: D1Database;
  USER_DATA: R2Bucket;         -- user upload bucket
  EXPORT_BUCKET: R2Bucket;     -- where compressed exports are stored
  MAILCHANNELS_API_KEY?: string; -- optional, for MailChannels Send API
  BASE_URL: string;            -- e.g. https://api.example.com
}

const SEVEN_DAYS_MS     = 7 * 24 * 60 * 60 * 1000;
const TWENTY_FOUR_H_MS  = 24 * 60 * 60 * 1000;

// ---------------------------------------------------------------------------
// Compression helper
// ---------------------------------------------------------------------------
async function compressJson(data: unknown): Promise<Uint8Array> {
  const json    = JSON.stringify(data, null, 2);
  const encoded = new TextEncoder().encode(json);
  const stream  = new Response(encoded).body!.pipeThrough(
    new CompressionStream('gzip')
  );
  const chunks: Uint8Array[] = [];
  const reader = stream.getReader();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  const total = chunks.reduce((a, c) => a + c.byteLength, 0);
  const out   = new Uint8Array(total);
  let offset  = 0;
  for (const c of chunks) { out.set(c, offset); offset += c.byteLength; }
  return out;
}

// ---------------------------------------------------------------------------
// Collect all D1 data for a user
// ---------------------------------------------------------------------------
async function collectUserData(env: Env, userId: string): Promise<Record<string, unknown>> {
  const [profile, sessions, orders] = await Promise.all([
    env.DB.prepare('SELECT * FROM user_profiles WHERE user_id = ?').bind(userId).all(),
    env.DB.prepare('SELECT id, created_at FROM user_sessions WHERE user_id = ?').bind(userId).all(),
    env.DB.prepare('SELECT * FROM orders WHERE user_id = ?').bind(userId).all(),
  ]);

  // Collect R2 upload metadata (not the objects themselves)
  const uploads: Array<{ key: string; size: number; uploaded: string }> = [];
  let cursor: string | undefined;
  do {
    const listed = await env.USER_DATA.list({
      prefix: `uploads/${userId}/`,
      cursor,
      limit: 1000,
    });
    uploads.push(
      ...listed.objects.map((o) => ({
        key:      o.key,
        size:     o.size,
        uploaded: o.uploaded.toISOString(),
      }))
    );
    cursor = listed.truncated ? listed.cursor : undefined;
  } while (cursor);

  return {
    export_version: '1.0',
    generated_at:   new Date().toISOString(),
    user_id:        userId,
    profile:        profile.results,
    sessions:       sessions.results,
    orders:         orders.results,
    uploads,
  };
}

// ---------------------------------------------------------------------------
// Email via MailChannels
// ---------------------------------------------------------------------------
async function sendDownloadEmail(
  env: Env,
  userId: string,
  downloadUrl: string
): Promise<void> {
  // Resolve email from D1
  const row = await env.DB
    .prepare('SELECT email FROM users WHERE id = ?')
    .bind(userId)
    .first<{ email: string }>();
  if (!row) return;

  await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: row.email }] }],
      from: { email: 'privacy@example.com', name: 'Privacy Team' },
      subject: 'Your data export is ready',
      content: [
        {
          type: 'text/plain',
          value:
            `Your personal data export is ready for download.\n\n` +
            `Download link (expires in 7 days):\n${downloadUrl}\n\n` +
            `If you did not request this export, please contact support.`,
        },
      ],
    }),
  });
}

// ---------------------------------------------------------------------------
// Main handler
// ---------------------------------------------------------------------------
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url    = new URL(request.url);
    const userId = await resolveUserId(request);  // your auth helper
    if (!userId) return new Response('Unauthorized', { status: 401 });

    // POST /v1/me/data-export — initiate export
    if (request.method === 'POST' && url.pathname === '/v1/me/data-export') {
      // Rate-limit check
      const rl = await env.DB
        .prepare('SELECT last_request_at FROM portability_rate_limit WHERE user_id = ?')
        .bind(userId)
        .first<{ last_request_at: number }>();
      if (rl && Date.now() - rl.last_request_at < TWENTY_FOUR_H_MS) {
        return Response.json(
          { error: 'rate_limited', retry_after_iso: new Date(rl.last_request_at + TWENTY_FOUR_H_MS).toISOString() },
          { status: 429 }
        );
      }

      const requestId = crypto.randomUUID();
      const now       = Date.now();

      await env.DB
        .prepare(`INSERT INTO portability_requests (id, user_id, requested_at) VALUES (?, ?, ?)`)
        .bind(requestId, userId, now)
        .run();

      await env.DB
        .prepare(
          `INSERT INTO portability_rate_limit (user_id, last_request_at)
           VALUES (?, ?)
           ON CONFLICT(user_id) DO UPDATE SET last_request_at = excluded.last_request_at`
        )
        .bind(userId, now)
        .run();

      // Build export
      await env.DB
        .prepare(`UPDATE portability_requests SET status = 'building' WHERE id = ?`)
        .bind(requestId)
        .run();

      const data       = await collectUserData(env, userId);
      const compressed = await compressJson(data);
      const r2Key      = `exports/${userId}/${requestId}.json.gz`;

      await env.EXPORT_BUCKET.put(r2Key, compressed, {
        httpMetadata: {
          contentType:     'application/gzip',
          contentEncoding: 'gzip',
        },
      });

      // Generate presigned URL (7-day TTL)
      const presignedUrl = await env.EXPORT_BUCKET.createPresignedUrl(r2Key, {
        expiresIn: Math.floor(SEVEN_DAYS_MS / 1000),
      });

      const urlExpiresAt = now + SEVEN_DAYS_MS;

      await env.DB
        .prepare(
          `UPDATE portability_requests
           SET status = 'complete', completed_at = ?, r2_key = ?,
               presigned_url = ?, url_expires_at = ?
           WHERE id = ?`
        )
        .bind(Date.now(), r2Key, presignedUrl, urlExpiresAt, requestId)
        .run();

      // Send email notification
      try {
        await sendDownloadEmail(env, userId, presignedUrl);
        await env.DB
          .prepare(`UPDATE portability_requests SET email_sent = 1 WHERE id = ?`)
          .bind(requestId)
          .run();
      } catch { /* email failure should not fail the export */ }

      return Response.json({
        request_id:     requestId,
        status:         'complete',
        download_url:   presignedUrl,
        expires_iso:    new Date(urlExpiresAt).toISOString(),
        size_bytes:     compressed.byteLength,
      });
    }

    // GET /v1/me/data-export — list previous requests
    if (request.method === 'GET' && url.pathname === '/v1/me/data-export') {
      const rows = await env.DB
        .prepare(
          `SELECT id, status, requested_at, url_expires_at, email_sent
           FROM portability_requests WHERE user_id = ? ORDER BY requested_at DESC LIMIT 10`
        )
        .bind(userId)
        .all();
      return Response.json(rows.results);
    }

    return new Response('Not Found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;

async function resolveUserId(_req: Request): Promise<string | null> {
  return 'user-123'; // replace with real auth
}
```

---

## Section 3 — Testing / Verification

```bash
# Initiate an export
curl -X POST https://api.example.com/v1/me/data-export \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"request_id":"...","status":"complete","download_url":"...","expires_iso":"..."}

# Download and inspect the export
curl -L "<download_url>" | gzip -d | python3 -m json.tool | head -50

# Verify R2 object exists
npx wrangler r2 object list EXPORT_BUCKET --prefix exports/user-123/

# Check audit table
npx wrangler d1 execute MY_DB \
  --command "SELECT id, status, email_sent, datetime(requested_at/1000,'unixepoch') FROM portability_requests ORDER BY requested_at DESC"

# Confirm rate-limit blocks a second request within 24h
curl -X POST https://api.example.com/v1/me/data-export \
  -H "Authorization: Bearer $TOKEN"
# Expected: HTTP 429 with retry_after_iso
```

---

## Anti-patterns

- **Including sensitive credentials or tokens in the export** — Scrub fields like `password_hash`, `mfa_secret`, and OAuth tokens from all exported rows.
- **Serving the export directly from the Worker response body** — Large exports will exceed streaming limits; always upload to R2 and return a presigned URL.
- **Not expiring the presigned URL** — An indefinitely valid download link is a security liability; 7 days balances usability with risk.
- **Forgetting to list R2 objects** — Users expect their uploaded files to be included; a profile-only export is incomplete under Article 20.
- **Skipping the rate limit** — Without rate limiting, a bad actor can enumerate data by repeatedly requesting exports.

---

## Gotchas

- `R2Bucket.createPresignedUrl()` is only available on the Paid Workers plan; on Free you must use the Cloudflare API to generate signed URLs out-of-band.
- `CompressionStream('gzip')` is available in the Workers runtime but not in Node.js test environments — mock it in Vitest or use `zlib` when running tests outside the Workers sandbox.
- D1 `Promise.all()` over multiple `.all()` calls is safe since D1 uses HTTP-based execution and supports concurrent queries.
- MailChannels Send API requires DNS SPF/DKIM records to be set; test in a sandbox domain first.
- Exports contain PII; the R2 bucket storing them must be private (no public access), and access logs should be enabled.

---

## Verification

```bash
# Confirm export is compressed
curl -s -o /tmp/export.gz "<download_url>"
file /tmp/export.gz  # should report: gzip compressed data
gzip -d /tmp/export.gz && wc -c /tmp/export

# Confirm URL expires correctly
date -d "+7 days"  # compare with expires_iso from API response

# List portability requests with their statuses
npx wrangler d1 execute MY_DB \
  --command "SELECT user_id, status, email_sent, r2_key FROM portability_requests"

# Confirm R2 key follows expected pattern
npx wrangler r2 object get EXPORT_BUCKET exports/user-123/<request_id>.json.gz
```

---

## Related

- `workers-gdpr-right-to-erasure-d1.md`
- `workers-ccpa-opt-out-gpc-header.md`
- `workers-hipaa-audit-log-d1.md`

---

## Sources

- GDPR Article 20 — https://gdpr-info.eu/art-20-gdpr/
- Cloudflare R2 Presigned URLs — https://developers.cloudflare.com/r2/api/workers/workers-api-usage/#create-a-presigned-url
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- MailChannels Send API — https://api.mailchannels.net/tx/v1/documentation
- Web Streams CompressionStream — https://developer.mozilla.org/en-US/docs/Web/API/CompressionStream
