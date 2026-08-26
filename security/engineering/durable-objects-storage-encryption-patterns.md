# Durable Objects Storage Encryption at Rest Patterns

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You store sensitive per-user or per-tenant data (PII, financial records, health data, session secrets) in Durable Objects. Cloudflare encrypts all stored data at the infrastructure level, but your compliance requirements (HIPAA, GDPR, PCI-DSS, SOC 2) mandate application-level encryption so that Cloudflare—or anyone with raw storage access—cannot read plaintext values. You need envelope encryption, key rotation, and auditable key management without introducing an external KMS that adds latency to every Durable Object operation.

---

## Context

Cloudflare Durable Objects provide persistent storage via the `DurableObjectStorage` API (`this.ctx.storage`). Values are serialised and stored as structured clones; they are encrypted at rest by Cloudflare using platform-managed keys, but application-level encryption adds a second layer that the platform cannot unwrap. The pattern below uses the Web Crypto API (`crypto.subtle`) available in both Workers and Durable Objects to implement AES-256-GCM envelope encryption with per-record nonces, wrapping data encryption keys (DEKs) with an account-level key encryption key (KEK) stored as a Worker Secret.

Key hierarchy:
- **KEK** (Key Encryption Key): 256-bit AES-GCM key stored as a Workers Secret (`wrangler secret put KEK_BASE64`). Never written to Durable Object storage.
- **DEK** (Data Encryption Key): 256-bit AES-GCM key generated per user/tenant, wrapped (encrypted) with the KEK, and stored alongside the ciphertext in Durable Object storage.
- **Nonce**: 96-bit random value generated per write operation; stored with the ciphertext.

---

## Key Generation and KEK Loading

```typescript
// durable-objects/src/crypto-utils.ts

const AES_GCM: AesKeyGenParams = { name: "AES-GCM", length: 256 };
const NONCE_LENGTH = 12; // 96 bits for AES-GCM

export async function loadKEK(kekBase64: string): Promise<CryptoKey> {
  const raw = Uint8Array.from(atob(kekBase64), c => c.charCodeAt(0));
  return crypto.subtle.importKey("raw", raw, AES_GCM, false, ["wrapKey", "unwrapKey"]);
}

export async function generateDEK(): Promise<CryptoKey> {
  return crypto.subtle.generateKey(AES_GCM, true /* extractable for wrapping */, [
    "encrypt",
    "decrypt",
  ]);
}

export async function wrapDEK(dek: CryptoKey, kek: CryptoKey): Promise<string> {
  const nonce = crypto.getRandomValues(new Uint8Array(NONCE_LENGTH));
  const wrapped = await crypto.subtle.wrapKey("raw", dek, kek, {
    name: "AES-GCM",
    iv: nonce,
  });
  // Store nonce + wrapped key as base64
  const combined = new Uint8Array(NONCE_LENGTH + wrapped.byteLength);
  combined.set(nonce, 0);
  combined.set(new Uint8Array(wrapped), NONCE_LENGTH);
  return btoa(String.fromCharCode(...combined));
}

export async function unwrapDEK(wrappedB64: string, kek: CryptoKey): Promise<CryptoKey> {
  const combined = Uint8Array.from(atob(wrappedB64), c => c.charCodeAt(0));
  const nonce = combined.slice(0, NONCE_LENGTH);
  const wrappedKey = combined.slice(NONCE_LENGTH);
  return crypto.subtle.unwrapKey(
    "raw",
    wrappedKey,
    kek,
    { name: "AES-GCM", iv: nonce },
    AES_GCM,
    false, /* non-extractable after unwrap */
    ["encrypt", "decrypt"]
  );
}
```

---

## Per-Record Encryption and Decryption

```typescript
// durable-objects/src/encrypt.ts
const NONCE_LENGTH = 12;

export async function encryptValue(
  plaintext: unknown,
  dek: CryptoKey
): Promise<string> {
  const json = JSON.stringify(plaintext);
  const data = new TextEncoder().encode(json);
  const nonce = crypto.getRandomValues(new Uint8Array(NONCE_LENGTH));

  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce },
    dek,
    data
  );

  const out = new Uint8Array(NONCE_LENGTH + ciphertext.byteLength);
  out.set(nonce, 0);
  out.set(new Uint8Array(ciphertext), NONCE_LENGTH);
  return btoa(String.fromCharCode(...out));
}

export async function decryptValue<T = unknown>(
  encryptedB64: string,
  dek: CryptoKey
): Promise<T> {
  const raw = Uint8Array.from(atob(encryptedB64), c => c.charCodeAt(0));
  const nonce = raw.slice(0, NONCE_LENGTH);
  const ciphertext = raw.slice(NONCE_LENGTH);

  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: nonce },
    dek,
    ciphertext
  );

  return JSON.parse(new TextDecoder().decode(plaintext)) as T;
}
```

---

## Durable Object with Envelope Encryption

```typescript
// durable-objects/src/EncryptedStore.ts
import { loadKEK, generateDEK, wrapDEK, unwrapDEK } from "./crypto-utils";
import { encryptValue, decryptValue } from "./encrypt";

interface Env {
  KEK_BASE64: string; // Workers Secret
}

const WRAPPED_DEK_KEY = "__wrapped_dek__";

export class EncryptedStore implements DurableObject {
  private storage: DurableObjectStorage;
  private kekBase64: string;
  private dekCache: CryptoKey | null = null;

  constructor(ctx: DurableObjectState, env: Env) {
    this.storage = ctx.storage;
    this.kekBase64 = env.KEK_BASE64;
  }

  // Lazily load or create the DEK for this Durable Object instance
  private async getDEK(): Promise<CryptoKey> {
    if (this.dekCache) return this.dekCache;

    const kek = await loadKEK(this.kekBase64);
    const existingWrapped = await this.storage.get<string>(WRAPPED_DEK_KEY);

    if (existingWrapped) {
      this.dekCache = await unwrapDEK(existingWrapped, kek);
    } else {
      const dek = await generateDEK();
      const wrapped = await wrapDEK(dek, kek);
      await this.storage.put(WRAPPED_DEK_KEY, wrapped);
      this.dekCache = await unwrapDEK(wrapped, kek); // re-import as non-extractable
    }

    return this.dekCache;
  }

  async setEncrypted(key: string, value: unknown): Promise<void> {
    if (key === WRAPPED_DEK_KEY) throw new Error("Reserved key");
    const dek = await this.getDEK();
    const encrypted = await encryptValue(value, dek);
    await this.storage.put(key, encrypted);
  }

  async getEncrypted<T>(key: string): Promise<T | null> {
    const encrypted = await this.storage.get<string>(key);
    if (!encrypted) return null;
    const dek = await this.getDEK();
    return decryptValue<T>(encrypted, dek);
  }

  async deleteEncrypted(key: string): Promise<void> {
    await this.storage.delete(key);
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "PUT") {
      const { key, value } = await request.json<{ key: string; value: unknown }>();
      await this.setEncrypted(key, value);
      return new Response("OK");
    }

    if (request.method === "GET") {
      const key = url.searchParams.get("key");
      if (!key) return new Response("Missing key", { status: 400 });
      const value = await this.getEncrypted(key);
      return new Response(JSON.stringify({ value }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("Method not allowed", { status: 405 });
  }
}
```

---

## KEK Rotation Without Re-encryption Downtime

When the KEK must be rotated (regular key rotation schedule, or suspected compromise), re-wrap each instance's DEK with the new KEK. The DEK itself does not change, so stored ciphertext is unaffected:

```typescript
// workers/src/rotate-kek.ts
// Run as a one-off Worker invoked by an admin endpoint or CI job

export async function rotateKEK(
  oldKEKBase64: string,
  newKEKBase64: string,
  doNamespace: DurableObjectNamespace,
  instanceIds: string[]
): Promise<void> {
  const oldKEK = await loadKEK(oldKEKBase64);
  const newKEK = await loadKEK(newKEKBase64);

  for (const id of instanceIds) {
    const stub = doNamespace.get(doNamespace.idFromName(id));
    const resp = await stub.fetch("https://internal/rotate-kek", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ oldKEKBase64, newKEKBase64 }),
    });
    if (!resp.ok) throw new Error(`KEK rotation failed for ${id}: ${resp.status}`);
  }
}

// Inside the Durable Object's fetch handler, handle /rotate-kek:
// 1. Unwrap current DEK with oldKEK
// 2. Re-wrap DEK with newKEK
// 3. Overwrite __wrapped_dek__ in storage
// 4. Clear dekCache
```

---

## Field-Level Encryption for Selective Plaintext Indexing

Sometimes you need to query on a field (e.g., email for lookup) while keeping its value encrypted. Store a keyed HMAC of the index field alongside the ciphertext:

```typescript
// durable-objects/src/index-hmac.ts

export async function hmacIndex(
  value: string,
  hmacKeyBase64: string
): Promise<string> {
  const keyBytes = Uint8Array.from(atob(hmacKeyBase64), c => c.charCodeAt(0));
  const key = await crypto.subtle.importKey(
    "raw", keyBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

// Store: await storage.put(`idx:email:${await hmacIndex(email, env.HMAC_KEY)}`, doId);
// Lookup: const doId = await storage.get(`idx:email:${await hmacIndex(email, env.HMAC_KEY)}`);
```

---

## Anti-patterns

- **Storing the KEK in Durable Object storage**: The KEK must live exclusively in Workers Secrets (`env.KEK_BASE64`). Storing it alongside the data it protects eliminates the encryption benefit.
- **Reusing nonces**: AES-GCM is catastrophically broken if a nonce is reused with the same key. Always generate a fresh `crypto.getRandomValues(new Uint8Array(12))` for every encryption call.
- **Using a single global DEK for all Durable Object instances**: Per-instance DEKs limit the blast radius of a single DEK compromise to one tenant/user.
- **Keeping DEK in memory across requests without clearing**: The `dekCache` in the example is safe within a single DO instance lifetime; do not share it across instances or serialise it.
- **Encrypting index fields with AES-GCM**: GCM produces different ciphertext for the same plaintext (due to random nonces), making equality lookups impossible. Use deterministic HMAC for indexed fields.

---

## Gotchas

- **`wrapKey` requires the DEK to be extractable**: Set `extractable: true` when generating the DEK; after wrapping and storing it, re-import as `extractable: false` for in-memory use.
- **AES-GCM tag length**: The default authentication tag is 128 bits (appended to ciphertext by SubtleCrypto). Your stored blob is `nonce(12) + ciphertext(n) + tag(16)` bytes.
- **Durable Object eviction**: The `dekCache` is an in-memory field; it is lost when the DO is evicted. The next request will unwrap from storage again—adding one `crypto.subtle.unwrapKey` call latency.
- **Storage transaction atomicity**: Use `this.storage.transaction()` when writing both the ciphertext and an index entry to ensure they are committed together.
- **KEK stored in Workers Secrets is not versioned**: Maintain your own version suffix in the secret name (`KEK_V2_BASE64`) during rotation to avoid mixing keys.

---

## Verification

```bash
# 1. Generate a test KEK and set as a secret
openssl rand -base64 32
wrangler secret put KEK_BASE64

# 2. Write an encrypted value via the DO
curl -X PUT https://your-worker.example.com/store \
  -H "Content-Type: application/json" \
  -d '{"key":"ssn","value":"123-45-6789"}'

# 3. Verify the raw storage value is not plaintext (use wrangler tail to inspect)
wrangler tail --format json | jq .

# 4. Read it back — should return decrypted
curl https://your-worker.example.com/store?key=ssn

# 5. Confirm a wrong KEK cannot decrypt (rotate to a new KEK, attempt decrypt with old — expect error)
```

---

## Related

- `encryption-at-rest-detail.md`
- `secrets-encryption-at-rest.md`
- `durable-objects-auth-patterns.md`
- `workers-secrets-store-scoped-binding.md`
- `cryptographic-agility-workers-subtlecrypto-migration.md`

---

## Sources

- Web Crypto API (AES-GCM): https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/encrypt
- Cloudflare Durable Objects storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- NIST SP 800-57 Key Management Guidelines: https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final
- Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
- AES-GCM envelope encryption pattern: https://developers.google.com/tink/tinkling-with-tink
