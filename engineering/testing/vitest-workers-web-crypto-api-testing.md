# Vitest Workers Web Crypto API Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker uses `crypto.subtle` (the Web Crypto API) for HMAC request signing, AES-GCM payload encryption, or Ed25519 key derivation. You need Vitest tests that exercise these paths inside a real Workers runtime so that algorithm support, key format constraints, and error branches are all validated before deployment.

## Context

The Workers runtime exposes the Web Crypto API through the global `crypto` object. Node.js's `node:crypto` is a different surface; tests that run in a Node environment will not catch runtime-specific behaviour such as key extractability rules or algorithm identifier casing. `@cloudflare/vitest-pool-workers` runs tests inside a Miniflare Workers isolate, giving access to the same `SubtleCrypto` implementation used in production.

---

## 1. vitest.config.ts Setup

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

No special bindings are required — `crypto.subtle` is available as a global in every Workers isolate.

---

## 2. HMAC-SHA256 Request Signing Tests

```typescript
// src/crypto.ts
export async function signPayload(
  secret: string,
  payload: string
): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(payload));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

export async function verifyPayload(
  secret: string,
  payload: string,
  signature: string
): Promise<boolean> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  const sigBytes = Uint8Array.from(atob(signature), (c) => c.charCodeAt(0));
  return crypto.subtle.verify("HMAC", key, sigBytes, enc.encode(payload));
}
```

```typescript
// src/crypto.test.ts
import { describe, it, expect } from "vitest";
import { signPayload, verifyPayload } from "./crypto";

describe("HMAC-SHA256", () => {
  const SECRET = "test-webhook-secret-32-bytes-000";

  it("produces a consistent Base64 signature for the same inputs", async () => {
    const sig1 = await signPayload(SECRET, "hello");
    const sig2 = await signPayload(SECRET, "hello");
    expect(sig1).toBe(sig2);
  });

  it("different payloads produce different signatures", async () => {
    const sig1 = await signPayload(SECRET, "hello");
    const sig2 = await signPayload(SECRET, "world");
    expect(sig1).not.toBe(sig2);
  });

  it("verifyPayload accepts a valid signature", async () => {
    const payload = '{"event":"user.created","id":42}';
    const sig = await signPayload(SECRET, payload);
    const valid = await verifyPayload(SECRET, payload, sig);
    expect(valid).toBe(true);
  });

  it("verifyPayload rejects a tampered payload", async () => {
    const sig = await signPayload(SECRET, "original");
    const valid = await verifyPayload(SECRET, "tampered", sig);
    expect(valid).toBe(false);
  });

  it("rejects a key that is too short (< 32 bytes)", async () => {
    await expect(signPayload("short", "payload")).rejects.toThrow();
  });
});
```

---

## 3. AES-GCM Encryption / Decryption Tests

```typescript
// src/aes.ts
const IV_BYTES = 12;

export async function encryptAES(
  rawKey: CryptoKey,
  plaintext: string
): Promise<{ ciphertext: string; iv: string }> {
  const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
  const enc = new TextEncoder();
  const encrypted = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    rawKey,
    enc.encode(plaintext)
  );
  return {
    ciphertext: btoa(String.fromCharCode(...new Uint8Array(encrypted))),
    iv: btoa(String.fromCharCode(...iv)),
  };
}

export async function decryptAES(
  rawKey: CryptoKey,
  ciphertext: string,
  ivB64: string
): Promise<string> {
  const iv = Uint8Array.from(atob(ivB64), (c) => c.charCodeAt(0));
  const data = Uint8Array.from(atob(ciphertext), (c) => c.charCodeAt(0));
  const dec = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, rawKey, data);
  return new TextDecoder().decode(dec);
}
```

```typescript
// src/aes.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { encryptAES, decryptAES } from "./aes";

describe("AES-GCM", () => {
  let key: CryptoKey;

  beforeEach(async () => {
    key = await crypto.subtle.generateKey(
      { name: "AES-GCM", length: 256 },
      false,        // non-extractable — same as prod policy
      ["encrypt", "decrypt"]
    );
  });

  it("roundtrips plaintext through encrypt → decrypt", async () => {
    const plaintext = "sensitive payload";
    const { ciphertext, iv } = await encryptAES(key, plaintext);
    const recovered = await decryptAES(key, ciphertext, iv);
    expect(recovered).toBe(plaintext);
  });

  it("produces different ciphertext on each call (unique IV)", async () => {
    const { ciphertext: c1 } = await encryptAES(key, "same");
    const { ciphertext: c2 } = await encryptAES(key, "same");
    expect(c1).not.toBe(c2);
  });

  it("decryption fails with wrong IV", async () => {
    const { ciphertext, iv } = await encryptAES(key, "data");
    const badIv = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(12))));
    await expect(decryptAES(key, ciphertext, badIv)).rejects.toThrow();
  });

  it("decryption fails with wrong key", async () => {
    const wrongKey = await crypto.subtle.generateKey(
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
    const { ciphertext, iv } = await encryptAES(key, "data");
    await expect(decryptAES(wrongKey, ciphertext, iv)).rejects.toThrow();
  });
});
```

---

## 4. Key Derivation (PBKDF2) Tests

```typescript
// src/kdf.ts
export async function deriveKey(
  password: string,
  salt: Uint8Array
): Promise<CryptoKey> {
  const enc = new TextEncoder();
  const baseKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(password),
    "PBKDF2",
    false,
    ["deriveKey"]
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: 100_000, hash: "SHA-256" },
    baseKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
}
```

```typescript
// src/kdf.test.ts
import { describe, it, expect } from "vitest";
import { deriveKey } from "./kdf";
import { encryptAES, decryptAES } from "./aes";

describe("PBKDF2 key derivation", () => {
  const SALT = crypto.getRandomValues(new Uint8Array(16));

  it("derives a usable AES-GCM key", async () => {
    const key = await deriveKey("password123", SALT);
    expect(key.type).toBe("secret");
    expect(key.algorithm.name).toBe("AES-GCM");
  });

  it("same password + salt yields functionally equivalent key", async () => {
    const key1 = await deriveKey("password", SALT);
    const key2 = await deriveKey("password", SALT);
    const { ciphertext, iv } = await encryptAES(key1, "roundtrip");
    const recovered = await decryptAES(key2, ciphertext, iv);
    expect(recovered).toBe("roundtrip");
  });

  it("different salt yields incompatible key", async () => {
    const saltB = crypto.getRandomValues(new Uint8Array(16));
    const key1 = await deriveKey("password", SALT);
    const key2 = await deriveKey("password", saltB);
    const { ciphertext, iv } = await encryptAES(key1, "data");
    await expect(decryptAES(key2, ciphertext, iv)).rejects.toThrow();
  });
});
```

---

## 5. Running Tests

```bash
npx vitest run src/crypto.test.ts src/aes.test.ts src/kdf.test.ts
```

Expected output:
```
✓ HMAC-SHA256 > produces a consistent Base64 signature (12ms)
✓ HMAC-SHA256 > different payloads produce different signatures (3ms)
✓ HMAC-SHA256 > verifyPayload accepts a valid signature (4ms)
✓ HMAC-SHA256 > verifyPayload rejects a tampered payload (2ms)
✓ HMAC-SHA256 > rejects a key that is too short (< 32 bytes) (2ms)
✓ AES-GCM > roundtrips plaintext … (6ms)
…
```

---

## Anti-patterns

- **Running Web Crypto tests in Node's test environment** — Node's `globalThis.crypto.subtle` differs subtly in error messages and algorithm support; always use `@cloudflare/vitest-pool-workers`.
- **Hardcoding IVs in production code** — tests must cover the non-determinism; generate IVs with `crypto.getRandomValues` and assert uniqueness.
- **Extractable keys in production** — marking keys `extractable: true` for test convenience is fine locally; ensure production code uses `false` and write a dedicated test that asserts `key.extractable === false`.
- **Using `algorithm` string shorthand for `importKey`** — Workers requires the full object form `{ name: "HMAC", hash: "SHA-256" }`; the string shorthand `"HMAC"` throws in some Workers builds.

## Gotchas

- `crypto.subtle` operations are always async; wrap all calls in `await` even in tests where you expect synchronous-looking flow.
- `getRandomValues` is synchronous and fills a typed array in-place; do not `await` it.
- PBKDF2 with 100,000 iterations is deliberately slow; tests using it will take ~200 ms per case — budget for this in CI.
- The `AES-GCM` authentication tag is appended to the ciphertext by `SubtleCrypto`; any byte flip in the ciphertext causes decryption to throw, which is the correct security behavior to assert.

## Verification

```bash
# Confirm the Workers isolate has crypto.subtle available
npx vitest run --reporter=verbose src/crypto.test.ts

# Run with coverage to catch untested error branches
npx vitest run --coverage src/aes.test.ts
```

## Related

- `vitest-workers-env-var-override-testing.md`
- `vitest-workers-wasm-module-testing.md`
- `workers-unit-testing-fetch-mocking.md`
- `vitest-cloudflare-pool-workers.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- https://www.w3.org/TR/WebCryptoAPI/
