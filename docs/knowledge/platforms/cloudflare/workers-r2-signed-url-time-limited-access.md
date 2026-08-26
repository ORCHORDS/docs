# Workers R2 Signed URL — Time-Limited Access

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You store private assets in an R2 bucket and need to hand short-lived download links to authenticated users without exposing the bucket publicly. Native R2 presigned URLs are not available from the Workers runtime, so you implement HMAC-SHA256 signing inside a Worker and verify the signature on every request.

---

## Context

R2 objects can be read from a Worker using the `R2Bucket` binding without making the bucket public. By signing a payload of `{bucket, key, expiry}` with a secret stored in Workers Secrets, you produce a token that proves the link was issued by your system and has not expired. The Worker that serves downloads re-derives the HMAC and rejects requests with a mismatched or past-expiry token. A D1 table logs every signed URL issued, giving you an audit trail for compliance. The trade-off versus a public bucket with access rules is that the Workers proxy approach keeps the bucket fully private at the cost of routing download traffic through a Worker on every request.

---

## Section 1 — wrangler.toml

```toml
name = "r2-signed-url-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[r2_buckets]]
binding = "ASSETS"
bucket_name = "private-assets"

[[d1_databases]]
binding = "DB"
database_name = "audit"
database_id = "<your-d1-id>"

[vars]
SIGNED_URL_TTL_SECONDS = "3600"

# Set via: wrangler secret put SIGNING_SECRET
# SIGNING_SECRET = "<random-32-byte-hex>"
```

---

## Section 2 — Implementation

```typescript
// src/lib/sign.ts
export async function importKey(secret: string): Promise<CryptoKey> {
  const enc = new TextEncoder();
  return crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
}

export async function signPayload(
  key: CryptoKey,
  payload: string
): Promise<string> {
  const enc = new TextEncoder();
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(payload));
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

export async function verifyPayload(
  key: CryptoKey,
  payload: string,
  token: string
): Promise<boolean> {
  const expected = await signPayload(key, payload);
  if (expected.length !== token.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= expected.charCodeAt(i) ^ token.charCodeAt(i);
  }
  return diff === 0;
}

// src/index.ts
export interface Env {
  ASSETS: R2Bucket;
  DB: D1Database;
  SIGNING_SECRET: string;
  SIGNED_URL_TTL_SECONDS: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /sign?key=<redacted-secret>  — issue a signed URL
    if (request.method === "POST" && url.pathname === "/sign") {
      return handleSign(request, env, url);
    }

    // GET /download?key=...&expiry=...&sig=...  — serve the object
    if (request.method === "GET" && url.pathname === "/download") {
      return handleDownload(request, env, url);
    }

    return new Response("Not found", { status: 404 });
  },
};

async function handleSign(
  request: Request,
  env: Env,
  url: URL
): Promise<Response> {
  const key = url.searchParams.get("key");
  if (!key) return new Response("Missing key", { status: 400 });

  const ttl = parseInt(env.SIGNED_URL_TTL_SECONDS, 10);
  const expiry = Math.floor(Date.now() / 1000) + ttl;
  const payload = `private-assets:${key}:${expiry}`;

  const cryptoKey = await importKey(env.SIGNING_SECRET);
  const sig = await signPayload(cryptoKey, payload);

  const signedUrl = `${url.origin}/download?key=<redacted-secret>&expiry=${expiry}&sig=${sig}`;

  await env.DB.prepare(
    `INSERT INTO signed_url_audit (object_key, expiry, created_at, issuer_ip)
     VALUES (?, ?, unixepoch(), ?)`
  )
    .bind(key, expiry, request.headers.get("cf-connecting-ip") ?? "unknown")
    .run();

  return Response.json({ url: signedUrl, expiresAt: new Date(expiry * 1000).toISOString() });
}

async function handleDownload(
  _request: Request,
  env: Env,
  url: URL
): Promise<Response> {
  const key = url.searchParams.get("key");
  const expiry = url.searchParams.get("expiry");
  const sig = url.searchParams.get("sig");

  if (!key || !expiry || !sig) {
    return new Response("Missing parameters", { status: 400 });
  }

  const now = Math.floor(Date.now() / 1000);
  if (parseInt(expiry, 10) < now) {
    return new Response("Link expired", { status: 403 });
  }

  const payload = `private-assets:${key}:${expiry}`;
  const cryptoKey = await importKey(env.SIGNING_SECRET);
  const valid = await verifyPayload(cryptoKey, payload, sig);

  if (!valid) {
    return new Response("Invalid signature", { status: 403 });
  }

  const object = await env.ASSETS.get(key);
  if (!object) return new Response("Not found", { status: 404 });

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("etag", object.httpEtag);

  return new Response(object.body, { headers });
}
```

---

## Section 3 — D1 Schema & Testing

```sql
-- migrations/0001_signed_url_audit.sql
CREATE TABLE IF NOT EXISTS signed_url_audit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  object_key  TEXT    NOT NULL,
  expiry      INTEGER NOT NULL,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  issuer_ip   TEXT
);
CREATE INDEX idx_sua_key ON signed_url_audit (object_key);
```

```bash
# Apply migration
wrangler d1 execute audit --file=migrations/0001_signed_url_audit.sql

# Issue a signed URL (local dev)
curl -X POST "http://localhost:8787/sign?key=<redacted-secret>

# Try an expired URL (manually set expiry in the past)
curl "http://localhost:8787/download?key=<redacted-secret>&expiry=1700000000&sig=fakesig"
# Expected: 403 Link expired

# Download with a valid URL returned from /sign
SIG_URL=$(curl -s -X POST "http://localhost:8787/sign?key=<redacted-secret> | jq -r .url)
curl -o q4.pdf "$SIG_URL"
```

---

## Anti-patterns

- **Public bucket with query-string tokens only** — Without HMAC verification, any token value is accepted; attackers enumerate or guess keys.
- **Storing the signing secret in `[vars]`** — `[vars]` are visible in the dashboard; always use `wrangler secret put` for secrets.
- **Not including the bucket name in the payload** — Tokens signed for one bucket could be replayed against another if you run multiple buckets.
- **Using `Date.now()` without integer truncation** — Sub-second drift causes signature mismatches when the sign and verify calls straddle a millisecond boundary.

---

## Gotchas

- `crypto.subtle` is available globally in Workers; no import needed.
- `R2Object.body` is a `ReadableStream`; pass it directly as the `Response` body — do not buffer large files.
- `writeHttpMetadata` copies `Content-Type`, `Cache-Control`, etc. from R2 metadata onto your response headers automatically.
- D1 `unixepoch()` returns UTC seconds; compare against `Math.floor(Date.now() / 1000)` on the JS side.
- The `btoa` / `String.fromCharCode` pattern is safe for up to 64 KB signatures; for larger arbitrary binary use a proper base64 helper.

---

## Verification

```bash
# Run worker locally
wrangler dev

# Confirm 403 on tampered signature
curl -v "http://localhost:8787/download?key=test.txt&expiry=9999999999&sig=AAAA"

# Confirm audit row was written
wrangler d1 execute audit --command "SELECT * FROM signed_url_audit ORDER BY id DESC LIMIT 5;"
```

---

## Related

- `workers-d1-foreign-keys-cascade-delete.md`
- `workers-hyperdrive-postgres-connection-pool.md`

---

## Sources

- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Web Crypto API (HMAC) — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign
- Cloudflare Workers Secrets — https://developers.cloudflare.com/workers/configuration/secrets/
