# Web Crypto API Client-Side Encryption on Cloudflare Pages

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You need to encrypt sensitive data in the browser before it ever reaches your Cloudflare Workers backend — end-to-end encryption for notes, files, or credentials — without shipping a third-party crypto library. The built-in `SubtleCrypto` API covers AES-GCM symmetric encryption, RSA-OAEP asymmetric key wrapping, HKDF key derivation, and ECDH key exchange, all available in every Cloudflare Pages environment with zero bundle cost.

---

## Context

`window.crypto.subtle` (the Web Crypto API) is a native browser API exposed as `crypto.subtle` in both browser and Cloudflare Workers/Pages Functions runtimes. Because Pages Functions share the Workers runtime, the same `SubtleCrypto` code that runs in the browser also runs in your edge functions — useful for server-side key derivation or envelope decryption without any Node.js crypto shim.

All `SubtleCrypto` operations are async (Promise-based). Keys are represented as opaque `CryptoKey` objects that cannot be accidentally serialised to a string; you must explicitly call `exportKey` when persistence is needed.

---

## Generating an AES-GCM Encryption Key

```typescript
// utils/crypto.ts

export async function generateAesKey(): Promise<CryptoKey> {
  return crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    true,   // extractable — set false if key never leaves memory
    ["encrypt", "decrypt"]
  );
}

export async function exportKey(key: CryptoKey): Promise<string> {
  const raw = await crypto.subtle.exportKey("raw", key);
  return btoa(String.fromCharCode(...new Uint8Array(raw)));
}

export async function importKey(b64: string): Promise<CryptoKey> {
  const raw = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  return crypto.subtle.importKey(
    "raw",
    raw,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
}
```

---

## Encrypting and Decrypting Data

Always generate a fresh 96-bit IV (nonce) per encryption. Prepend the IV to the ciphertext so the decryption side can split it off.

```typescript
// utils/crypto.ts (continued)

const IV_BYTES = 12; // 96 bits — recommended for AES-GCM

export async function encrypt(
  key: CryptoKey,
  plaintext: string
): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
  const encoded = new TextEncoder().encode(plaintext);

  const cipherBuf = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    encoded
  );

  // Pack: iv (12 bytes) + ciphertext
  const combined = new Uint8Array(iv.byteLength + cipherBuf.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(cipherBuf), iv.byteLength);

  return btoa(String.fromCharCode(...combined));
}

export async function decrypt(
  key: CryptoKey,
  packed: string
): Promise<string> {
  const combined = Uint8Array.from(atob(packed), (c) => c.charCodeAt(0));
  const iv = combined.slice(0, IV_BYTES);
  const cipherBuf = combined.slice(IV_BYTES);

  const plainBuf = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv },
    key,
    cipherBuf
  );
  return new TextDecoder().decode(plainBuf);
}
```

---

## HKDF Key Derivation from a Password

Deriving a strong key from a user passphrase avoids storing raw keys and enables password-based encryption (PBE).

```typescript
// utils/pbkdf.ts

export async function deriveKeyFromPassword(
  password: string,
  salt: Uint8Array
): Promise<CryptoKey> {
  const baseKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveKey"]
  );

  return crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt,
      iterations: 310_000,   // OWASP 2023 recommendation
      hash: "SHA-256",
    },
    baseKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
}

// Usage
const salt = crypto.getRandomValues(new Uint8Array(16));
const key = await deriveKeyFromPassword("hunter2", salt);
// Persist salt alongside the ciphertext; re-derive key on next login
```

---

## Key Wrapping for Secure Storage

Wrap (encrypt) a content key with a key-encryption key (KEK) before storing it. This is the envelope encryption pattern used by AWS KMS, GCP KMS, and Cloudflare Workers secrets.

```typescript
// utils/keyWrap.ts

export async function wrapKey(
  contentKey: CryptoKey,
  kek: CryptoKey
): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const wrappedBuf = await crypto.subtle.wrapKey(
    "raw",
    contentKey,
    kek,
    { name: "AES-GCM", iv }
  );
  const combined = new Uint8Array(12 + wrappedBuf.byteLength);
  combined.set(iv);
  combined.set(new Uint8Array(wrappedBuf), 12);
  return btoa(String.fromCharCode(...combined));
}

export async function unwrapKey(
  wrapped: string,
  kek: CryptoKey
): Promise<CryptoKey> {
  const combined = Uint8Array.from(atob(wrapped), (c) => c.charCodeAt(0));
  const iv = combined.slice(0, 12);
  const wrappedBuf = combined.slice(12);
  return crypto.subtle.unwrapKey(
    "raw",
    wrappedBuf,
    kek,
    { name: "AES-GCM", iv },
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
}
```

---

## Mirroring Crypto in a Cloudflare Pages Function

Because Workers share the `SubtleCrypto` API, the same utils work server-side for envelope decryption before forwarding to a D1 query.

```typescript
// functions/api/notes.ts

import { decrypt } from "../../utils/crypto";

export const onRequestPost: PagesFunction<Env> = async (ctx) => {
  const { encryptedKey, payload } = await ctx.request.json<{
    encryptedKey: string;
    payload: string;
  }>();

  // Server holds master KEK in an env secret, never sent to the client
  const kekRaw = Uint8Array.from(
    atob(ctx.env.MASTER_KEK_B64),
    (c) => c.charCodeAt(0)
  );
  const masterKek = await crypto.subtle.importKey(
    "raw",
    kekRaw,
    { name: "AES-GCM", length: 256 },
    false,
    ["decrypt", "unwrapKey"]
  );

  // Unwrap the per-note content key the client sent
  const { unwrapKey } = await import("../../utils/keyWrap");
  const contentKey = await unwrapKey(encryptedKey, masterKek);
  const plaintext = await decrypt(contentKey, payload);

  await ctx.env.DB.prepare(
    "INSERT INTO notes (content) VALUES (?)"
  ).bind(plaintext).run();

  return new Response(JSON.stringify({ ok: true }), {
    headers: { "Content-Type": "application/json" },
  });
};
```

---

## Anti-patterns

- **Reusing IVs with the same key**: AES-GCM is catastrophically broken when (key, IV) pairs repeat. Always use `crypto.getRandomValues` per encryption call.
- **Storing raw keys in `localStorage`**: Base64-encoded key material in localStorage is readable by any script on the page. Use `wrapKey` with a KEK derived from the user's password or stored in a `non-extractable` CryptoKey instead.
- **Low PBKDF2 iteration counts**: Fewer than 100 000 iterations makes offline dictionary attacks trivial. Use 310 000+ (SHA-256) as of 2023 OWASP guidance.
- **Rolling your own authenticated encryption**: Prefer AES-GCM over AES-CBC; GCM provides built-in authentication tags. Never use AES-ECB.
- **Ignoring the `extractable` flag**: Set `extractable: false` for keys that never need to be exported; this prevents accidental serialisation.

---

## Gotchas

- `SubtleCrypto` is only available in secure contexts (`https://` or `localhost`). Cloudflare Pages always serves over HTTPS, so this is rarely an issue in production.
- `btoa`/`atob` silently corrupts non-Latin-1 data. Always pass `Uint8Array` to/from these helpers via the patterns shown above, never raw strings.
- `crypto.subtle.importKey` with `"raw"` format rejects keys that are not exactly 128, 192, or 256 bits for AES. Validate length before importing.
- Workers runtime `crypto` is the global `crypto` object — no `window.` prefix needed, same as in browsers.
- `wrapKey` requires the content key to have been created with `extractable: true`. Plan this before key generation.

---

## Verification

```typescript
// Smoke test in browser console or Vitest (happy-dom)
const key = await generateAesKey();
const ciphertext = await encrypt(key, "hello world");
const result = await decrypt(key, ciphertext);
console.assert(result === "hello world", "Round-trip failed");

// PBKDF2 round-trip
const salt = crypto.getRandomValues(new Uint8Array(16));
const derivedKey = await deriveKeyFromPassword("secret", salt);
const ct = await encrypt(derivedKey, "test");
const pt = await decrypt(derivedKey, ct);
console.assert(pt === "test", "PBKDF2 round-trip failed");
```

Run in a Pages Function via `wrangler pages dev` to validate Workers-side parity.

---

## Related

- `browser-web-workers.md` — offload heavy crypto work to a Worker thread to avoid blocking the main thread
- `cloudflare-pages-middleware-auth-gating.md` — gate routes using edge JWT verification
- `trusted-types-xss-prevention-workers.md` — prevent XSS that could steal key material
- `web-components-cloudflare-workers-html-rewriter.md` — inject nonces / CSP headers

---

## Sources

- MDN Web Docs — SubtleCrypto: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- Cloudflare Workers Runtime APIs — Web Crypto: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- W3C Web Cryptography API spec: https://www.w3.org/TR/WebCryptoAPI/
