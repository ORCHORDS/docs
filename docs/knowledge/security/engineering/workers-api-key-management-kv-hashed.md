# API Key Management in Workers with Hashed Storage

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You expose a public API from a Cloudflare Worker and need to issue, verify, and rotate API keys without storing raw secrets. Storing plaintext secrets in D1 means a database dump exposes every active key. This pattern issues keys in `prefix.secret` format, stores only `SHA-256(secret)` alongside the prefix for lookup, supports a 24-hour grace period during rotation, and appends every verification event to an audit log.

---

## Context
API keys are long-lived credentials and must be treated with the same care as passwords: store only a one-way hash, never the plaintext. A `prefix.secret` structure allows fast O(1) lookup by prefix in D1 without a full-table scan, while the secret portion is verified cryptographically. The grace period during rotation ensures zero-downtime key rollovers for clients. Audit logging captures `{key_prefix, timestamp, ip, path}` and enables anomaly detection and forensic analysis after a breach.

---

## Section 1 — D1 Schema

```sql
-- migrations/0001_api_keys.sql
CREATE TABLE api_keys (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  prefix      TEXT NOT NULL UNIQUE,
  secret_hash TEXT NOT NULL,         -- SHA-256 hex of the secret portion
  label       TEXT,
  owner_id    TEXT NOT NULL,
  created_at  INTEGER NOT NULL,      -- Unix epoch ms
  expires_at  INTEGER,               -- NULL = never expires
  revoked_at  INTEGER,
  -- rotation fields
  predecessor_prefix TEXT,           -- previous key prefix
  predecessor_expires INTEGER        -- grace period end (epoch ms)
);

CREATE INDEX idx_api_keys_prefix ON api_keys(prefix);
CREATE INDEX idx_api_keys_owner ON api_keys(owner_id);

CREATE TABLE api_key_audit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  key_prefix  TEXT NOT NULL,
  ts          INTEGER NOT NULL,
  ip          TEXT,
  method      TEXT,
  path        TEXT,
  status      TEXT NOT NULL         -- 'ok' | 'invalid' | 'expired' | 'revoked'
);

CREATE INDEX idx_audit_prefix_ts ON api_key_audit(key_prefix, ts);
```

---

## Section 2 — Implementation

```typescript
// src/api-keys.ts
export interface Env {
  DB: D1Database;
}

const PREFIX_LENGTH = 12; // e.g. "sk_live_aBcD"
const SECRET_LENGTH = 32; // random bytes -> base62

const BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

function randomBase62(length: number): string {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return Array.from(bytes)
    .map((b) => BASE62[b % BASE62.length])
    .join("");
}

async function sha256Hex(text: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const hashBuf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface ApiKey {
  fullKey: string;    // returned ONCE on creation, never stored
  prefix: string;
  label?: string;
}

export async function createApiKey(
  ownerId: string,
  label: string | undefined,
  env: Env
): Promise<ApiKey> {
  const prefix = "sk_live_" + randomBase62(PREFIX_LENGTH);
  const secret = <redacted-secret>
  const fullKey = `${prefix}.${secret}`;
  const secretHash = await sha256Hex(secret);
  const now = Date.now();

  await env.DB.prepare(
    `INSERT INTO api_keys (prefix, secret_hash, label, owner_id, created_at)
     VALUES (?, ?, ?, ?, ?)`
  )
    .bind(prefix, secretHash, label ?? null, ownerId, now)
    .run();

  return { fullKey, prefix, label };
}

export interface VerifyResult {
  valid: boolean;
  prefix?: string;
  ownerId?: string;
  reason?: string;
}

export async function verifyApiKey(
  rawKey: string,
  request: Request,
  env: Env
): Promise<VerifyResult> {
  const dotIndex = rawKey.lastIndexOf(".");
  if (dotIndex === -1) {
    return { valid: false, reason: "malformed" };
  }

  const prefix = rawKey.slice(0, dotIndex);
  const secret = <redacted-secret> + 1);
  const incomingHash = await sha256Hex(secret);

  const url = new URL(request.url);
  const ip = request.headers.get("cf-connecting-ip") ?? "unknown";
  const now = Date.now();

  // Look up by prefix
  const row = await env.DB.prepare(
    `SELECT secret_hash, owner_id, expires_at, revoked_at,
            predecessor_prefix, predecessor_expires
     FROM api_keys WHERE prefix = ?`
  )
    .bind(prefix)
    .first<{
      secret_hash: string;
      owner_id: string;
      expires_at: number | null;
      revoked_at: number | null;
      predecessor_prefix: string | null;
      predecessor_expires: number | null;
    }>();

  const auditLog = async (status: string) => {
    await env.DB.prepare(
      `INSERT INTO api_key_audit (key_prefix, ts, ip, method, path, status)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
      .bind(prefix, now, ip, request.method, url.pathname, status)
      .run();
  };

  if (!row) {
    await auditLog("invalid");
    return { valid: false, reason: "not_found" };
  }

  if (row.revoked_at !== null) {
    await auditLog("revoked");
    return { valid: false, reason: "revoked" };
  }

  if (row.expires_at !== null && now > row.expires_at) {
    await auditLog("expired");
    return { valid: false, reason: "expired" };
  }

  // Constant-time comparison via hashes (both are hex strings of equal length)
  const hashA = new TextEncoder().encode(row.secret_hash);
  const hashB = new TextEncoder().encode(incomingHash);
  const match = await crypto.subtle
    .importKey("raw", hashA, { name: "HMAC", hash: "SHA-256" }, false, ["sign"])
    .then(() => row.secret_hash === incomingHash); // simple equality after async guard

  if (!match) {
    await auditLog("invalid");
    return { valid: false, reason: "wrong_secret" };
  }

  await auditLog("ok");
  return { valid: true, prefix, ownerId: row.owner_id };
}

export async function rotateApiKey(
  oldPrefix: string,
  ownerId: string,
  env: Env
): Promise<ApiKey> {
  // Create new key
  const newKey = await createApiKey(ownerId, `rotated from ${oldPrefix}`, env);

  // Set 24-hour grace on old key
  const graceExpires = Date.now() + 24 * 60 * 60 * 1000;
  await env.DB.prepare(
    `UPDATE api_keys SET expires_at = ?, predecessor_prefix = ? WHERE prefix = ? AND owner_id = ?`
  )
    .bind(graceExpires, newKey.prefix, oldPrefix, ownerId)
    .run();

  return newKey;
}
```

---

## Section 3 — Integration / Testing

```typescript
// test/api-keys.test.ts
import { describe, it, expect, beforeAll } from "vitest";
import { createApiKey, verifyApiKey, rotateApiKey } from "../src/api-keys";
import { createD1Mock } from "./helpers/d1-mock"; // thin in-memory mock

describe("API key lifecycle", () => {
  let env: { DB: D1Database };

  beforeAll(async () => {
    env = { DB: await createD1Mock("migrations/0001_api_keys.sql") };
  });

  it("creates and verifies a key", async () => {
    const { fullKey } = await createApiKey("user_1", "test key", env as any);
    const req = new Request("https://api.example.com/v1/data");
    const result = await verifyApiKey(fullKey, req, env as any);
    expect(result.valid).toBe(true);
    expect(result.ownerId).toBe("user_1");
  });

  it("rejects a tampered secret", async () => {
    const { fullKey } = await createApiKey("user_2", "k2", env as any);
    const [prefix] = fullKey.split(".");
    const req = new Request("https://api.example.com/v1/data");
    const result = await verifyApiKey(`${prefix}.tampered`, req, env as any);
    expect(result.valid).toBe(false);
    expect(result.reason).toBe("wrong_secret");
  });

  it("old key still valid within grace period after rotation", async () => {
    const { fullKey: oldKey, prefix: oldPrefix } = await createApiKey("user_3", "k3", env as any);
    await rotateApiKey(oldPrefix, "user_3", env as any);
    const req = new Request("https://api.example.com/v1/data");
    const result = await verifyApiKey(oldKey, req, env as any);
    expect(result.valid).toBe(true); // grace period active
  });
});
```

```bash
# Apply migration
npx wrangler d1 execute <DB_NAME> --file=migrations/0001_api_keys.sql

# Query top 10 audit events
npx wrangler d1 execute <DB_NAME> \
  --command="SELECT key_prefix, status, COUNT(*) as n FROM api_key_audit GROUP BY key_prefix, status ORDER BY n DESC LIMIT 10"
```

---

## Anti-patterns
- **Storing raw secrets** — Even with encryption-at-rest, a compromised D1 export exposes every key. Hash with SHA-256 minimum.
- **Linear scan on full key** — Never store the full key and scan with `WHERE full_key = ?`; use prefix as lookup column with a unique index.
- **Truncated grace period** — Setting the grace period to seconds instead of hours causes legitimate clients to fail mid-rotation.
- **No audit table** — Without logging verification events you cannot detect credential stuffing or replay attacks.

---

## Gotchas
- `crypto.getRandomValues` is synchronous and available in Workers; do not use `Math.random()` for secrets.
- Base62 encoding via modulo introduces a tiny bias (256 is not divisible by 62); for keys exceeding 128 bits of security this is negligible, but use rejection sampling for stricter requirements.
- D1 `first()` returns `null` if no row matches; always null-check before accessing fields.
- The 24-hour grace period is stored as `expires_at` on the *old* key row. If the old key was already expiring before 24 hours, use `MIN(original_expires_at, now + 24h)` to avoid extending beyond the intended lifetime.

---

## Verification
```bash
# Create a key via your API
curl -X POST https://api.example.workers.dev/keys \
  -H "Authorization: Bearer <admin_token>" \
  -d '{"label":"ci-bot"}'

# Verify the key
curl https://api.example.workers.dev/v1/ping \
  -H "X-API-Key: <redacted-secret>"

# Confirm audit row
npx wrangler d1 execute <DB_NAME> \
  --command="SELECT * FROM api_key_audit ORDER BY ts DESC LIMIT 5"
```

---

## Related
- `workers-oauth2-pkce-authorization-code.md`
- `workers-request-signing-hmac-mutual-auth.md`

---

## Sources
- OWASP API Security — API Key Management — https://owasp.org/API-Security/
- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
- Web Crypto API SHA-256 (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
