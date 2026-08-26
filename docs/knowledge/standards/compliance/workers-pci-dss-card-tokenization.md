# PCI DSS Card Tokenization in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to accept raw PANs (Primary Account Numbers) from a checkout flow, tokenize them in a Cloudflare Worker to reduce PCI DSS scope, store the ciphertext in D1, and return only an opaque token to the caller so the PAN never persists in application logs, databases in clear text, or HTTP responses.

---

## Context

PCI DSS Requirement 3 prohibits storing sensitive authentication data after authorisation and mandates strong cryptography for stored PANs. Workers Secrets provide a hardware-backed key that never appears in source code or logs. AES-256-GCM authenticated encryption ensures both confidentiality and integrity of the stored ciphertext. The token is a random UUID with no mathematical relationship to the PAN, minimising the blast radius of a token database breach. Only the last four digits and expiry are stored in plaintext for display purposes.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS card_tokens (
  token           TEXT PRIMARY KEY,           -- UUID v4, returned to caller
  encrypted_pan   TEXT NOT NULL,              -- base64(iv || ciphertext || authTag)
  last4           TEXT NOT NULL,              -- last 4 digits of PAN, display only
  expiry          TEXT NOT NULL,              -- MM/YY, display only
  card_brand      TEXT,                       -- 'visa' | 'mastercard' | etc.
  created_at      INTEGER NOT NULL,
  last_used_at    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_ct_created ON card_tokens(created_at);

-- Tokenization audit (no PAN, no encrypted data)
CREATE TABLE IF NOT EXISTS tokenization_log (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  token       TEXT NOT NULL REFERENCES card_tokens(token),
  event       TEXT NOT NULL,   -- 'created' | 'used' | 'revoked'
  actor_id    TEXT,
  ip          TEXT,
  ts          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tl_token ON tokenization_log(token, ts);
```

---

## Section 2 — Worker Implementation

```typescript
interface Env {
  DB: D1Database;
  // Workers Secret — set with: wrangler secret put CARD_ENCRYPTION_KEY
  // Value must be a 32-byte random key encoded as hex (64 hex chars)
  CARD_ENCRYPTION_KEY: string;
}

// ---------------------------------------------------------------------------
// Crypto helpers
// ---------------------------------------------------------------------------
async function importAesKey(hexKey: string): Promise<CryptoKey> {
  const raw = hexToBytes(hexKey);
  return crypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, [
    'encrypt',
    'decrypt',
  ]);
}

function hexToBytes(hex: string): Uint8Array {
  const len = hex.length / 2;
  const out = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

function bytesToBase64(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}

function base64ToBytes(b64: string): Uint8Array {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

async function encryptPan(pan: string, key: CryptoKey): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12)); // 96-bit IV for GCM
  const encoded = new TextEncoder().encode(pan);
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    encoded
  );
  // Concatenate IV + ciphertext (includes 16-byte auth tag appended by SubtleCrypto)
  const combined = new Uint8Array(iv.byteLength + ciphertext.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(ciphertext), iv.byteLength);
  return bytesToBase64(combined.buffer);
}

async function decryptPan(encryptedB64: string, key: CryptoKey): Promise<string> {
  const combined = base64ToBytes(encryptedB64);
  const iv         = combined.slice(0, 12);
  const ciphertext = combined.slice(12);
  const plain = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    key,
    ciphertext
  );
  return new TextDecoder().decode(plain);
}

function detectBrand(pan: string): string {
  if (/^4/.test(pan))             return 'visa';
  if (/^5[1-5]/.test(pan))       return 'mastercard';
  if (/^3[47]/.test(pan))        return 'amex';
  if (/^6(?:011|5)/.test(pan))   return 'discover';
  return 'unknown';
}

function validatePan(pan: string): boolean {
  // Luhn algorithm
  const digits = pan.replace(/\D/g, '');
  if (digits.length < 13 || digits.length > 19) return false;
  let sum = 0;
  let alt = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let n = parseInt(digits[i], 10);
    if (alt) { n *= 2; if (n > 9) n -= 9; }
    sum += n;
    alt = !alt;
  }
  return sum % 10 === 0;
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /v1/tokenize — accepts { pan, expiry } returns { token, last4, brand }
    if (request.method === 'POST' && url.pathname === '/v1/tokenize') {
      let body: { pan?: string; expiry?: string };
      try {
        body = await request.json();
      } catch {
        return new Response('Bad JSON', { status: 400 });
      }

      const { pan, expiry } = body;
      if (!pan || !expiry) {
        return new Response('Missing pan or expiry', { status: 400 });
      }

      const cleanPan = pan.replace(/\s/g, '');

      if (!validatePan(cleanPan)) {
        return new Response('Invalid PAN', { status: 422 });
      }

      const aesKey = await importAesKey(env.CARD_ENCRYPTION_KEY);
      const encryptedPan = await encryptPan(cleanPan, aesKey);
      const token  = crypto.randomUUID();
      const last4  = cleanPan.slice(-4);
      const brand  = detectBrand(cleanPan);
      const now    = Date.now();

      await env.DB
        .prepare(
          `INSERT INTO card_tokens (token, encrypted_pan, last4, expiry, card_brand, created_at)
           VALUES (?, ?, ?, ?, ?, ?)`
        )
        .bind(token, encryptedPan, last4, expiry, brand, now)
        .run();

      await env.DB
        .prepare(
          `INSERT INTO tokenization_log (token, event, ip, ts)
           VALUES (?, 'created', ?, ?)`
        )
        .bind(token, request.headers.get('CF-Connecting-IP') ?? null, now)
        .run();

      // IMPORTANT: return ONLY token, last4, brand — never echo pan back
      return Response.json({ token, last4, card_brand: brand }, { status: 201 });
    }

    // GET /v1/tokens/:token — retrieve metadata (no PAN returned)
    if (request.method === 'GET' && url.pathname.startsWith('/v1/tokens/')) {
      const token = url.pathname.split('/').pop() ?? '';
      const row = await env.DB
        .prepare(
          `SELECT token, last4, expiry, card_brand, created_at FROM card_tokens WHERE token = ?`
        )
        .bind(token)
        .first();
      if (!row) return new Response('Not Found', { status: 404 });
      return Response.json(row);
    }

    return new Response('Not Found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — Testing / Verification

```typescript
import { describe, it, expect } from 'vitest';
import { env, createExecutionContext, waitOnExecutionContext } from 'cloudflare:test';
import worker from './index';

describe('PCI tokenization', () => {
  it('returns token without PAN in response', async () => {
    const ctx = createExecutionContext();
    const req = new Request('https://api.example.com/v1/tokenize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pan: '4111111111111111', expiry: '12/28' }),
    });
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(res.status).toBe(201);
    const body = await res.json<Record<string, string>>();
    expect(body.token).toMatch(/^[0-9a-f-]{36}$/);
    expect(body.last4).toBe('1111');
    expect(body.card_brand).toBe('visa');
    expect(body).not.toHaveProperty('pan');
    expect(body).not.toHaveProperty('encrypted_pan');
  });

  it('rejects invalid PAN', async () => {
    const ctx = createExecutionContext();
    const req = new Request('https://api.example.com/v1/tokenize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pan: '1234567890123456', expiry: '12/28' }),
    });
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);
    expect(res.status).toBe(422);
  });
});
```

---

## Anti-patterns

- **Logging the PAN** — Never log `pan`, even at debug level; Workers logs are persisted and may be exported.
- **Storing unencrypted PAN in D1** — Even truncated PANs beyond last-4 are considered sensitive; full PANs in cleartext are a critical PCI violation.
- **Using a symmetric key hard-coded in source** — Always use `wrangler secret put` so the key is stored in Cloudflare's encrypted secret store, not in `wrangler.toml` or version control.
- **Reusing IVs** — `crypto.getRandomValues` generates a fresh 96-bit IV per encryption; never reuse an IV with the same key under AES-GCM.
- **Returning encrypted_pan in any API response** — Only the token and display fields (last4, brand, expiry) should leave the Worker.

---

## Gotchas

- Workers `crypto.subtle` is synchronous-looking but returns Promises; always `await`.
- AES-GCM appends a 16-byte authentication tag to the ciphertext automatically in SubtleCrypto — account for this in your stored length expectations.
- D1 stores `TEXT` as UTF-8; base64 is the correct encoding for binary ciphertext blobs.
- PCI DSS scope applies to *all* systems that store, process, or transmit cardholder data — ensure your Worker is deployed in a zone isolated from non-compliant systems.
- Key rotation requires re-encrypting all stored PANs; plan for a `key_version` column from day one.

---

## Verification

```bash
# Tokenize a test PAN
curl -X POST https://api.example.com/v1/tokenize \
  -H "Content-Type: application/json" \
  -d '{"pan":"4111111111111111","expiry":"12/28"}'

# Confirm only token + last4 in response (no PAN field)
# Expected: {"token":"<uuid>","last4":"1111","card_brand":"visa"}

# Confirm encrypted_pan is NOT null in D1 but not exposed via API
npx wrangler d1 execute MY_DB \
  --command "SELECT token, last4, card_brand, length(encrypted_pan) AS enc_len FROM card_tokens LIMIT 5"

# Rotate encryption key (requires re-encryption script)
npx wrangler secret put CARD_ENCRYPTION_KEY
```

---

## Related

- `workers-hipaa-audit-log-d1.md`
- `workers-gdpr-right-to-erasure-d1.md`

---

## Sources

- PCI DSS v4.0 Requirement 3 — https://www.pcisecuritystandards.org/document_library/
- Web Crypto API (AES-GCM) — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/encrypt
- Cloudflare Workers Secrets — https://developers.cloudflare.com/workers/configuration/secrets/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
