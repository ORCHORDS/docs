# workers-crypto-patterns

**Issue:** Using Web Crypto API in Cloudflare Workers — common patterns without Node.js
**Date:** 2026-08-11
**Status:** documented

## Available in Workers

Cloudflare Workers runs the Web Crypto API (`crypto.subtle`). Node.js `crypto` module is NOT available.

Available algorithms: AES-GCM, AES-CBC, AES-KW, RSA-OAEP, RSA-PSS, ECDH, ECDSA, HMAC, PBKDF2, HKDF, SHA-256/384/512.

## UUID generation

```typescript
const id = crypto.randomUUID();
// → '550e8400-e29b-41d4-a716-446655440000'

// Compact: strip hyphens
const shortId = crypto.randomUUID().replace(/-/g, '');
// → '550e8400e29b41d4a716446655440000'

// Prefixed IDs:
const userId = `usr_${crypto.randomUUID().replace(/-/g, '').slice(0, 24)}`;
```

## HMAC-SHA256 (webhook signatures, API signing)

```typescript
async function hmacSha256Hex(message: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message));
  return Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

## SHA-256 hash (content fingerprinting, ETags)

```typescript
async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

## AES-GCM encryption (at-rest sensitive values)

```typescript
async function encrypt(plaintext: string, keyMaterial: string): Promise<string> {
  const rawKey = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(keyMaterial));
  const key = await crypto.subtle.importKey('raw', rawKey, { name: 'AES-GCM' }, false, ['encrypt']);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(plaintext),
  );
  // Encode as: base64(iv) + ':' + base64(ciphertext)
  const b64 = (buf: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(buf)));
  return `${b64(iv.buffer)}:${b64(ct)}`;
}

async function decrypt(ciphertext: string, keyMaterial: string): Promise<string> {
  const [ivB64, ctB64] = ciphertext.split(':');
  const iv = Uint8Array.from(atob(ivB64), c => c.charCodeAt(0));
  const ct = Uint8Array.from(atob(ctB64), c => c.charCodeAt(0));
  const rawKey = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(keyMaterial));
  const key = await crypto.subtle.importKey('raw', rawKey, { name: 'AES-GCM' }, false, ['decrypt']);
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct);
  return new TextDecoder().decode(pt);
}
```

## RSA key generation (SAML/JWT signing)

```typescript
// Generate RSA-PSS key pair for signing
const keypair = await crypto.subtle.generateKey(
  { name: 'RSA-PSS', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' },
  true,
  ['sign', 'verify'],
) as CryptoKeyPair;  // Must cast — generateKey returns CryptoKey | CryptoKeyPair

// Export as JWK for storage
const privateJwk = await crypto.subtle.exportKey('jwk', keypair.privateKey) as JsonWebKey;
const publicJwk = await crypto.subtle.exportKey('jwk', keypair.publicKey) as JsonWebKey;

// Import from JWK (after reading from KV/D1)
const privateKey = await crypto.subtle.importKey(
  'jwk', privateJwk,
  { name: 'RSA-PSS', hash: 'SHA-256' },
  false,
  ['sign'],
);
```

## RSA-PSS signing (SAML assertions, JWTs)

```typescript
async function rsaSign(privateKey: CryptoKey, data: Uint8Array): Promise<Uint8Array> {
  const sig = await crypto.subtle.sign(
    { name: 'RSA-PSS', saltLength: 32 },
    privateKey,
    data,
  );
  return new Uint8Array(sig);
}
```

## PBKDF2 key derivation (password hashing)

```typescript
async function deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveKey'],
  );
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: 310_000, hash: 'SHA-256' },
    base,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
}
```

## Random bytes / tokens

```typescript
// Random token (API key, SCIM token, reset link):
function randomToken(bytes = 32): string {
  const buf = crypto.getRandomValues(new Uint8Array(bytes));
  return Array.from(buf).map(b => b.toString(16).padStart(2, '0')).join('');
  // → 64-char hex string for 32 bytes
}

// URL-safe base64 token:
function randomBase64UrlToken(bytes = 32): string {
  const buf = crypto.getRandomValues(new Uint8Array(bytes));
  return btoa(String.fromCharCode(...buf)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}
```

## Gotchas

- **`generateKey` returns `CryptoKey | CryptoKeyPair`**: TypeScript won't narrow this — always cast `as CryptoKeyPair` when using asymmetric algorithms.
- **`exportKey` returns `ArrayBuffer | JsonWebKey`**: Cast `as JsonWebKey` when you expect JWK format.
- **`crypto.getRandomValues` is sync**: Unlike most crypto.subtle APIs, `getRandomValues` is synchronous. Don't `await` it.
- **No `Buffer` in Workers**: Use `Uint8Array` / `ArrayBuffer`. `btoa`/`atob` work for base64. For hex, use `toString(16).padStart(2, '0')` loop.
- **AES-GCM IV must be unique**: Never reuse an IV with the same key. Always generate a fresh random IV per encryption operation.
- **IV size**: AES-GCM standard IV is 12 bytes (96 bits). Don't use other sizes.
- **Key derivation from environment secrets**: When using an env var as key material, always run it through SHA-256 (or PBKDF2) first — env var strings are not uniform-random.

## Related

- `timing-safe-compare.md`
- `saml-sp-workers.md`
- `workers-types-migration.md`
- `d1-typescript-patterns.md`
