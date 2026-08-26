# Data Subject Access Request (DSAR) Fulfillment Pipeline in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Under GDPR Article 15, CCPA, and other privacy laws, users have the right to request a copy of all personal data you hold about them. You need an automated DSAR pipeline that: accepts the request, verifies the requester's identity, aggregates personal data from D1 (relational), R2 (file storage), and KV (session/preferences), packages everything into a structured JSON export, stores the export in R2 with a time-limited signed URL, and tracks the 30-day statutory deadline — all within a single Cloudflare Workers application.

## Context

Manual DSAR fulfillment is error-prone and slow. GDPR mandates a 30-day response window (extendable to 90 days for complex requests). A missed deadline can trigger regulatory complaints and fines. Key pipeline stages:

1. **Intake** — user submits email + proof of identity token
2. **Identity verification** — validate token against D1 user record
3. **Aggregation** — query every data store for records matching the user
4. **Export** — compose structured JSON bundle
5. **Delivery** — store in R2, generate presigned URL, email user
6. **Deadline tracking** — record in D1 with `due_at` timestamp, mark complete when fulfilled

## Solution

```typescript
export interface Env {
  DB: D1Database;              // User data and DSAR tracking
  USER_DATA_BUCKET: R2Bucket;  // File uploads and DSAR exports
  USER_KV: KVNamespace;        // Per-user KV namespace
  DSAR_SIGNING_SECRET: string; // HMAC secret for presigned URLs
  BASE_URL: string;            // e.g. "https://api.example.com"
}

const DSAR_DEADLINE_DAYS = 30;
const EXPORT_URL_TTL_SECONDS = 60 * 60 * 24 * 7; // 7 days to download

// ─── Identity verification ────────────────────────────────────────────────────

interface VerifyResult {
  valid: boolean;
  userId?: string;
  email?: string;
  reason?: string;
}

async function verifyIdentity(
  env: Env,
  email: string,
  token: string
): Promise<VerifyResult> {
  // Token is a one-time code emailed during DSAR submission
  const row = await env.DB.prepare(
    `SELECT id, email, dsar_verify_token, dsar_verify_expires_at
     FROM users
     WHERE email = ? AND dsar_verify_token = ? AND dsar_verify_expires_at > ?`
  )
    .bind(email, token, new Date().toISOString())
    .first<{ id: string; email: string }>();

  if (!row) {
    return { valid: false, reason: 'Invalid or expired verification token' };
  }

  // Burn the token
  await env.DB.prepare(
    `UPDATE users SET dsar_verify_token = NULL, dsar_verify_expires_at = NULL WHERE id = ?`
  )
    .bind(row.id)
    .run();

  return { valid: true, userId: row.id, email: row.email };
}

// ─── Data aggregation ─────────────────────────────────────────────────────────

interface DsarExport {
  requestId: string;
  generatedAt: string;
  subject: { userId: string; email: string };
  data: {
    profile: unknown;
    orders: unknown[];
    sessions: unknown[];
    consents: unknown[];
    auditLog: unknown[];
    files: Array<{ key: string; size: number; uploaded: string }>;
    preferences: Record<string, string>;
  };
}

async function aggregateUserData(
  env: Env,
  userId: string,
  email: string,
  requestId: string
): Promise<DsarExport> {
  // ── D1 queries (run in parallel) ─────────────────────────────────────────
  const [profile, orders, sessions, consents, auditLog] = await Promise.all([
    env.DB.prepare(`SELECT * FROM users WHERE id = ?`)
      .bind(userId)
      .first(),

    env.DB.prepare(
      `SELECT id, created_at, total_cents, status, shipping_address
       FROM orders WHERE user_id = ? ORDER BY created_at DESC`
    )
      .bind(userId)
      .all()
      .then((r) => r.results),

    env.DB.prepare(
      `SELECT id, created_at, ip_address, user_agent, expires_at
       FROM user_sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT 100`
    )
      .bind(userId)
      .all()
      .then((r) => r.results),

    env.DB.prepare(
      `SELECT purpose, granted, timestamp, source
       FROM consent_log WHERE user_id = ? ORDER BY timestamp DESC`
    )
      .bind(userId)
      .all()
      .then((r) => r.results),

    env.DB.prepare(
      `SELECT action, resource, timestamp, ip_address
       FROM audit_log WHERE user_id = ? ORDER BY timestamp DESC LIMIT 500`
    )
      .bind(userId)
      .all()
      .then((r) => r.results),
  ]);

  // ── R2: list all objects under user prefix ────────────────────────────────
  const r2List = await env.USER_DATA_BUCKET.list({
    prefix: `users/${userId}/`,
    limit: 1000,
  });
  const files = r2List.objects.map((obj) => ({
    key: obj.key,
    size: obj.size,
    uploaded: obj.uploaded.toISOString(),
  }));

  // ── KV: list all keys under user namespace ────────────────────────────────
  const kvList = await env.USER_KV.list({ prefix: `user:${userId}:` });
  const preferences: Record<string, string> = {};
  await Promise.all(
    kvList.keys.map(async (k) => {
      const val = await env.USER_KV.get(k.name);
      if (val !== null) preferences[k.name] = val;
    })
  );

  return {
    requestId,
    generatedAt: new Date().toISOString(),
    subject: { userId, email },
    data: {
      profile: sanitizeProfile(profile),
      orders: orders as unknown[],
      sessions: sessions as unknown[],
      consents: consents as unknown[],
      auditLog: auditLog as unknown[],
      files,
      preferences,
    },
  };
}

function sanitizeProfile(profile: unknown): unknown {
  if (!profile || typeof profile !== 'object') return profile;
  // Remove internal fields not relevant to the data subject
  const { password_hash, mfa_secret, ...safe } = profile as Record<string, unknown>;
  return safe;
}

// ─── Presigned URL generation ─────────────────────────────────────────────────

async function generatePresignedUrl(
  env: Env,
  r2Key: string,
  ttlSeconds: number
): Promise<string> {
  const expiresAt = Math.floor(Date.now() / 1000) + ttlSeconds;
  const payload = `${r2Key}|${expiresAt}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(env.DSAR_SIGNING_SECRET),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload));
  const sigHex = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return `${env.BASE_URL}/dsar/download/${encodeURIComponent(r2Key)}?expires=${expiresAt}&sig=${sigHex}`;
}

// ─── Signed URL validation (download endpoint) ───────────────────────────────

async function validatePresignedUrl(
  env: Env,
  r2Key: string,
  expires: number,
  sig: string
): Promise<boolean> {
  if (Date.now() / 1000 > expires) return false;
  const payload = `${r2Key}|${expires}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(env.DSAR_SIGNING_SECRET),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const expected = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload));
  const expectedHex = Array.from(new Uint8Array(expected))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return expectedHex === sig;
}

// ─── Deadline tracking in D1 ──────────────────────────────────────────────────

async function createDsarRecord(
  env: Env,
  requestId: string,
  userId: string,
  email: string
): Promise<void> {
  const dueAt = new Date();
  dueAt.setDate(dueAt.getDate() + DSAR_DEADLINE_DAYS);
  await env.DB.prepare(
    `INSERT INTO dsar_requests (id, user_id, email, status, requested_at, due_at)
     VALUES (?, ?, ?, 'pending', ?, ?)`
  )
    .bind(requestId, userId, email, new Date().toISOString(), dueAt.toISOString())
    .run();
}

async function markDsarComplete(
  env: Env,
  requestId: string,
  exportKey: string,
  downloadUrl: string
): Promise<void> {
  await env.DB.prepare(
    `UPDATE dsar_requests
     SET status = 'completed', completed_at = ?, export_r2_key = ?, download_url = ?
     WHERE id = ?`
  )
    .bind(new Date().toISOString(), exportKey, downloadUrl, requestId)
    .run();
}

// ─── Main Worker ───────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /dsar/request — initiate DSAR
    if (request.method === 'POST' && url.pathname === '/dsar/request') {
      const { email, token } = await request.json<{ email: string; token: string }>();
      const verify = await verifyIdentity(env, email, token);
      if (!verify.valid) {
        return new Response(JSON.stringify({ error: verify.reason }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      const requestId = crypto.randomUUID();
      await createDsarRecord(env, requestId, verify.userId!, verify.email!);

      // Run aggregation (may take a few seconds — use a Durable Object or Queue for prod)
      const exportData = await aggregateUserData(env, verify.userId!, verify.email!, requestId);
      const exportJson = JSON.stringify(exportData, null, 2);
      const exportKey = `dsar/${requestId}/export.json`;

      await env.USER_DATA_BUCKET.put(exportKey, exportJson, {
        httpMetadata: { contentType: 'application/json' },
        customMetadata: { userId: verify.userId!, requestId },
      });

      const downloadUrl = await generatePresignedUrl(env, exportKey, EXPORT_URL_TTL_SECONDS);
      await markDsarComplete(env, requestId, exportKey, downloadUrl);

      return new Response(
        JSON.stringify({ requestId, downloadUrl, expiresInDays: 7 }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // GET /dsar/download/:key — serve export file
    if (request.method === 'GET' && url.pathname.startsWith('/dsar/download/')) {
      const r2Key = decodeURIComponent(url.pathname.replace('/dsar/download/', ''));
      const expires = Number(url.searchParams.get('expires'));
      const sig = url.searchParams.get('sig') ?? '';

      if (!(await validatePresignedUrl(env, r2Key, expires, sig))) {
        return new Response('Link expired or invalid', { status: 403 });
      }

      const obj = await env.USER_DATA_BUCKET.get(r2Key);
      if (!obj) return new Response('Not found', { status: 404 });

      return new Response(obj.body, {
        headers: {
          'Content-Type': 'application/json',
          'Content-Disposition': 'attachment; filename="data-export.json"',
        },
      });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Implementation Details

**D1 parallel queries**: All five D1 queries run via `Promise.all` to minimise latency. Each query is scoped strictly to the requesting user's ID — no cross-user data leakage.

**R2 prefix listing**: `list({ prefix: 'users/{userId}/' })` returns up to 1,000 object metadata records. Paginate with `cursor` for users with large file stores.

**KV namespace listing**: `list({ prefix: 'user:{userId}:' })` returns key metadata. Each value is fetched individually. For large KV stores, consider a secondary index.

**Presigned URLs**: HMAC-SHA-256 over `{r2Key}|{expiresAt}` provides tamper-proof, time-limited URLs without requiring R2 presigned URL feature (which requires a different bucket config).

**30-day deadline**: Stored as `due_at` in the `dsar_requests` D1 table. A separate scheduled Worker should query `SELECT * FROM dsar_requests WHERE status = 'pending' AND due_at < datetime('now')` and alert your DPO.

**D1 schema additions**:
```sql
CREATE TABLE dsar_requests (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  email TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  requested_at TEXT NOT NULL,
  due_at TEXT NOT NULL,
  completed_at TEXT,
  export_r2_key TEXT,
  download_url TEXT
);
ALTER TABLE users ADD COLUMN dsar_verify_token TEXT;
ALTER TABLE users ADD COLUMN dsar_verify_expires_at TEXT;
```

## Anti-patterns

- **Do not** fulfill DSAR without identity verification — anyone who knows an email could exfiltrate another user's data.
- **Do not** store the export indefinitely in R2; delete it after the download TTL expires using a scheduled Worker.
- **Do not** include password hashes, MFA secrets, or internal system fields in the export; `sanitizeProfile` strips these.
- **Do not** run `SELECT *` from tables containing other users' data — always filter by `user_id`.
- **Do not** handle the aggregation synchronously for large accounts; use a Cloudflare Queue to offload and notify via email when ready.

## Gotchas

- **CPU time limit**: Workers have a 30-second CPU limit (50ms on the free plan). For users with many records, move aggregation to a Durable Object with longer compute time or a Queue consumer.
- **R2 list pagination**: The `list()` call returns a `truncated` flag; loop with `cursor` to retrieve all objects.
- **KV list limit**: `list()` returns a max of 1,000 keys per call; paginate with `cursor` for power users.
- **Token burn race condition**: Two concurrent DSAR verifications with the same token could both succeed before the burn completes. Use a D1 transaction with `BEGIN EXCLUSIVE` to prevent this in high-traffic scenarios.
- **GDPR Art. 15(4)**: The right of access must not adversely affect the rights of others — redact third-party personal data in shared records (e.g., a user who placed an order on behalf of someone else).

## Verification

```bash
# 1. Initiate DSAR (after issuing a verify token to the test user)
curl -X POST https://api.example.com/dsar/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@example.com","token":"abc123xyz"}'
# Expected: {"requestId":"...","downloadUrl":"...","expiresInDays":7}

# 2. Download the export
curl -L "<downloadUrl>" -o export.json
jq '.data | keys' export.json
# Expected: ["auditLog","consents","files","orders","preferences","profile","sessions"]

# 3. Verify profile does not contain secrets
jq '.data.profile | has("password_hash")' export.json
# Expected: false

# 4. Check deadline record in D1
wrangler d1 execute <DB_NAME> --command \
  "SELECT id, status, due_at FROM dsar_requests ORDER BY requested_at DESC LIMIT 1;"
```

## Related

- `documentation/docs/policies/compliance/workers-retention-policy-enforcer.md` — after DSAR-requested deletion
- `documentation/docs/policies/compliance/gdpr-data-deletion-pipeline.md` — right to erasure (Art. 17)
- `documentation/docs/policies/compliance/gdpr-consent-logging.md` — consent records included in DSAR export
- `documentation/docs/policies/compliance/audit-log-immutable-r2.md` — audit log sourced in DSAR
- `documentation/docs/policies/compliance/workers-access-control-audit.md` — access log included in DSAR

## Sources

- GDPR Article 15 — Right of access by the data subject
- GDPR Recital 63 — Right of access
- ICO DSAR guidance: https://ico.org.uk/for-organisations/guide-to-data-protection/guide-to-the-general-data-protection-regulation-gdpr/individual-rights/right-of-access/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Cloudflare R2: https://developers.cloudflare.com/r2/
- Cloudflare KV: https://developers.cloudflare.com/kv/
