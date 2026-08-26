# Encrypting KV Values with AES-256-GCM in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You store sensitive data (PII, secrets, tokens) in Cloudflare KV but want cryptographic protection at rest so that a KV namespace compromise does not expose plaintext values. You need transparent encrypt-on-write / decrypt-on-read with a master secret stored as a Worker secret, and a migration path for key rotation.

---

## Context
AES-256-GCM provides authenticated encryption — it both encrypts and integrity-checks the ciphertext, so tampering is detectable. A unique 12-byte IV is generated per encryption call and stored alongside the ciphertext. The per-KV-key encryption key is derived with HKDF from a master secret plus the KV key name as salt, so different KV entries use different derived keys even with the same master. Key rotation requires a migration script that decrypts with the old master and re-encrypts with the new one.

---

## Encryption / Decryption Helpers
```typescript
// src/crypto-kv.ts
const GCM_IV_LENGTH  = 12; // bytes
const GCM_TAG_LENGTH = 128; // bits

interface EncryptedValue {
  iv:         string; // base64url
  ciphertext: string; // base64url (includes GCM auth tag)
  v:          number; // schema version for future rotation
}

function toB64(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

function fromB64(s: string): Uint8Array {
  return Uint8Array.from(
    atob(s.replace(/-/g, '+').replace(/_/g, '/')),
    c => c.charCodeAt(0)
  );
}

async function deriveKey(masterSecret: string, kvKey: string): Promise<CryptoKey> {
  // Import master as HKDF key material
  const masterKeyMaterial = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(masterSecret),
    { name: 'HKDF' },
    false,
    ['deriveKey']
  );

  // Derive a per-KV-entry AES-256-GCM key using the KV key as info
  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: new TextEncoder().encode('kv-encryption-v1'),
      info: new TextEncoder().encode(kvKey),
    },
    masterKeyMaterial,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  );
}

export async function encrypt(
  plaintext: string,
  masterSecret: string,
  kvKey: string
): Promise<string> {
  const key = await deriveKey(masterSecret, kvKey);

  const iv = crypto.getRandomValues(new Uint8Array(GCM_IV_LENGTH));
  const cipherBuf = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, tagLength: GCM_TAG_LENGTH },
    key,
    new TextEncoder().encode(plaintext)
  );

  const envelope: EncryptedValue = {
    iv:         toB64(iv),
    ciphertext: toB64(cipherBuf),
    v:          1,
  };
  return JSON.stringify(envelope);
}

export async function decrypt(
  stored: string,
  masterSecret: string,
  kvKey: string
): Promise<string> {
  const envelope = JSON.parse(stored) as EncryptedValue;
  if (envelope.v !== 1) throw new Error(`Unknown encryption schema version: ${envelope.v}`);

  const key        = await deriveKey(masterSecret, kvKey);
  const iv         = fromB64(envelope.iv);
  const cipherBuf  = fromB64(envelope.ciphertext);

  const plainBuf = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv, tagLength: GCM_TAG_LENGTH },
    key,
    cipherBuf
  );

  return new TextDecoder().decode(plainBuf);
}
```

---

## Worker: Encrypted KV Read/Write
```typescript
// src/index.ts
import type { Env } from './env';
import { encrypt, decrypt } from './crypto-kv';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const kvKey = url.searchParams.get('key');
    if (!kvKey) return new Response('Missing key param', { status: 400 });

    if (request.method === 'PUT') {
      const plaintext = await request.text();
      const encrypted = await encrypt(plaintext, env.KV_MASTER_SECRET, kvKey);
      await env.SECURE_KV.put(kvKey, encrypted);
      return new Response('OK');
    }

    if (request.method === 'GET') {
      const stored = await env.SECURE_KV.get(kvKey);
      if (!stored) return new Response('Not Found', { status: 404 });
      try {
        const plaintext = await decrypt(stored, env.KV_MASTER_SECRET, kvKey);
        return new Response(plaintext);
      } catch {
        return new Response('Decryption failed', { status: 500 });
      }
    }

    return new Response('Method Not Allowed', { status: 405 });
  },
};
```

---

## Key Rotation Migration Script
```typescript
// scripts/rotate-kv-keys.ts
// Run with: npx tsx scripts/rotate-kv-keys.ts
import { encrypt, decrypt } from '../src/crypto-kv';

// Provide these via environment
const OLD_SECRET = process.env.OLD_KV_MASTER_SECRET!;
const NEW_SECRET = process.env.NEW_KV_MASTER_SECRET!;
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const NAMESPACE_ID = process.env.KV_NAMESPACE_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;

const BASE = `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${NAMESPACE_ID}`;
const HEADERS = { Authorization: `Bearer ${API_TOKEN}` };

async function listKeys(cursor?: string): Promise<{ keys: { name: string }[]; cursor?: string; done: boolean }> {
  const url = `${BASE}/keys${cursor ? `?cursor=${cursor}` : ''}`;
  const resp = await fetch(url, { headers: HEADERS });
  const data = await resp.json<any>();
  return {
    keys:   data.result,
    cursor: data.result_info?.cursor,
    done:   !data.result_info?.cursor,
  };
}

async function main() {
  let cursor: string | undefined;
  let migrated = 0;

  do {
    const { keys, cursor: nextCursor, done } = await listKeys(cursor);
    cursor = nextCursor;

    for (const { name } of keys) {
      const getResp = await fetch(`${BASE}/values/${encodeURIComponent(name)}`, { headers: HEADERS });
      const stored = await getResp.text();

      // Skip non-encrypted values
      if (!stored.startsWith('{')) continue;

      const plaintext = await decrypt(stored, OLD_SECRET, name);
      const newEncrypted = await encrypt(plaintext, NEW_SECRET, name);

      await fetch(`${BASE}/values/${encodeURIComponent(name)}`, {
        method: 'PUT',
        headers: { ...HEADERS, 'Content-Type': 'text/plain' },
        body: newEncrypted,
      });

      migrated++;
      console.log(`Rotated: ${name}`);
    }
  } while (!cursor);

  console.log(`Migration complete. Rotated ${migrated} keys.`);
}

main().catch(console.error);
```

---

## wrangler.toml
```toml
[[kv_namespaces]]
binding = "SECURE_KV"
id      = "<KV_NAMESPACE_ID>"
```

```bash
wrangler secret put KV_MASTER_SECRET
```

---

## Anti-patterns
- **Reusing the IV** — a repeated IV with the same key breaks GCM security catastrophically; always generate a fresh random IV per encryption call.
- **Using the same derived key for all KV entries** — derive per-entry keys with HKDF so a single entry's key compromise is isolated.
- **Storing the master secret in `[vars]`** — use `wrangler secret put` so it is encrypted at rest by Cloudflare and not visible in wrangler.toml.
- **Skipping the auth tag check** — AES-GCM `decrypt` throws on tampered ciphertext automatically; do not suppress the error.

---

## Gotchas
- `crypto.subtle.decrypt` throws a `DOMException` (not a generic `Error`) when the GCM tag fails; catch broadly or the Worker will surface a 500.
- KV values have a 25 MB size limit; the base64-encoded ciphertext is ~33% larger than the plaintext.
- HKDF `info` is not a secret — it differentiates key usage contexts, not provides additional secrecy.
- The migration script uses the Cloudflare REST API which has rate limits; add delays between batches for large namespaces.

---

## Verification
```bash
# Set secrets locally for dev
echo 'MY_MASTER_SECRET_32_BYTES_MINIMUM!' | wrangler secret put KV_MASTER_SECRET

# Write an encrypted value
curl -X PUT 'https://<worker>.workers.dev/?key=<redacted-secret> \
  -d 'This is sensitive content'

# Read and decrypt
curl 'https://<worker>.workers.dev/?key=<redacted-secret>
# Expect: This is sensitive content

# Inspect raw KV value (should be JSON with iv + ciphertext)
wrangler kv key get --binding SECURE_KV my-secret-data
# Expect: {"iv":"...","ciphertext":"...","v":1}

# Run key rotation
OLD_KV_MASTER_SECRET=old NEW_KV_MASTER_SECRET=new \
CF_ACCOUNT_ID=<id> KV_NAMESPACE_ID=<ns-id> CF_API_TOKEN=<token> \
npx tsx scripts/rotate-kv-keys.ts
```

---

## Related
- `workers-api-key-rotation-kv-d1.md`
- `workers-csp-reporting-endpoint-d1.md`

---

## Sources
- Web Crypto API AES-GCM — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/encrypt
- HKDF Key Derivation — https://developer.mozilla.org/en-US/docs/Web/API/HkdfParams
- Cloudflare KV Docs — https://developers.cloudflare.com/kv/
- NIST SP 800-38D (GCM) — https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf
