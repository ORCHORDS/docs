# Mocking crypto.subtle in Vitest Workers Pool Tests

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers code signs JWTs, derives HKDF keys, or produces HMAC digests using the
`crypto.subtle` Web Crypto API. You need deterministic unit tests that:
- Return fixed key material or digests without real cryptographic computation
- Test error branches (e.g., unsupported algorithm, invalid key length)
- Run fast in CI without entropy concerns or hardware-backed key store access

## Context

In the `@cloudflare/vitest-pool-workers` environment, `crypto` is the Workers-runtime
`globalThis.crypto` — a real `Crypto` object backed by BoringSSL. `vi.spyOn` can intercept
individual `SubtleCrypto` methods because they are ordinary JS functions on the
`crypto.subtle` object (not native bindings at the JS level). The spy must be installed
before the module under test calls `crypto.subtle`; in Workers pool tests the recommended
place is a `beforeEach` or `beforeAll` in the test file. `vi.restoreAllMocks()` in
`afterEach` cleans up between tests.

## 1. Project Setup

```jsonc
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
  },
});
```

## 2. Spying on digest()

The simplest case: stub `crypto.subtle.digest` to return a fixed 32-byte value.

```typescript
// src/hash.ts
export async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const buf  = await crypto.subtle.digest('SHA-256', data);
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}
```

```typescript
// src/hash.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { sha256Hex } from './hash';

const FIXED_DIGEST = new Uint8Array(32).fill(0xab).buffer;

describe('sha256Hex', () => {
  beforeEach(() => {
    vi.spyOn(crypto.subtle, 'digest').mockResolvedValue(FIXED_DIGEST);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('formats the digest as lowercase hex', async () => {
    const result = await sha256Hex('anything');
    expect(result).toBe('ab'.repeat(32));
  });

  it('passes the correct algorithm and encoded data to digest', async () => {
    await sha256Hex('hello');
    expect(crypto.subtle.digest).toHaveBeenCalledWith(
      'SHA-256',
      expect.any(Uint8Array),
    );
  });
});
```

## 3. Spying on importKey + sign (HMAC)

Test HMAC signing logic without generating real keys:

```typescript
// src/hmac.ts
export async function hmacSign(secret: string, message: string): Promise<string> {
  const keyMaterial = new TextEncoder().encode(secret);
  const key = await crypto.subtle.importKey(
    'raw', keyMaterial,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}
```

```typescript
// src/hmac.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { hmacSign } from './hmac';

describe('hmacSign', () => {
  const FAKE_KEY = {} as CryptoKey;
  const FAKE_SIG = new Uint8Array([1, 2, 3, 255]).buffer;

  beforeEach(() => {
    vi.spyOn(crypto.subtle, 'importKey').mockResolvedValue(FAKE_KEY);
    vi.spyOn(crypto.subtle, 'sign').mockResolvedValue(FAKE_SIG);
  });

  afterEach(() => vi.restoreAllMocks());

  it('calls sign with the fake key', async () => {
    await hmacSign('s3cr3t', 'payload');
    expect(crypto.subtle.sign).toHaveBeenCalledWith('HMAC', FAKE_KEY, expect.any(Uint8Array));
  });

  it('returns base64 of the fake signature bytes', async () => {
    const result = await hmacSign('s3cr3t', 'payload');
    expect(result).toBe(btoa('\x01\x02\x03\xff'));
  });
});
```

## 4. Testing Error Branches

Force `DOMException` to test error handling:

```typescript
// src/hmac.test.ts (additional cases)
it('surfaces crypto errors to the caller', async () => {
  vi.spyOn(crypto.subtle, 'importKey').mockRejectedValue(
    new DOMException('Invalid key data', 'DataError'),
  );

  await expect(hmacSign('bad-key', 'msg')).rejects.toThrow('Invalid key data');
});
```

## 5. Using Real Test Vectors Without Mocking

When you want integration-level confidence without mocking, use known HMAC-SHA256 test
vectors from RFC 4231. This is slower but verifies algorithm correctness end-to-end:

```typescript
// src/hmac.integration.test.ts
import { describe, it, expect } from 'vitest';
import { hmacSign } from './hmac';

// RFC 4231 Test Case 1 (truncated for illustration)
it('produces correct HMAC-SHA256 for RFC 4231 test case 1', async () => {
  const key    = '\x0b'.repeat(20);
  const data   = 'Hi There';
  const result = await hmacSign(key, data);
  // Expected base64 of 0xb0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7
  expect(result).toBe('sDRMYdjbOFNcqK/Or wv...'); // replace with real value
});
```

## 6. Mocking generateKey for Key-Pair Flows

```typescript
// test helper
export function mockGenerateKey(): { publicKey: CryptoKey; privateKey: CryptoKey } {
  const pair = {
    publicKey:  { type: 'public',  algorithm: { name: 'ECDSA' } } as CryptoKey,
    privateKey: { type: 'private', algorithm: { name: 'ECDSA' } } as CryptoKey,
  };
  vi.spyOn(crypto.subtle, 'generateKey').mockResolvedValue(pair);
  return pair;
}
```

## Anti-patterns

- **`vi.mock('crypto', ...)`** — `crypto` is a global in the Workers runtime, not a Node
  module. Module mocking has no effect; use `vi.spyOn(crypto.subtle, ...)` instead.
- **Mocking `crypto.getRandomValues`** — this is on `crypto` directly, not `subtle`. Use
  `vi.spyOn(crypto, 'getRandomValues').mockImplementation(...)`.
- **Sharing a spy across test files without `vi.restoreAllMocks()`** — Workers pool tests
  may share an isolate; a spy left installed in one test bleeds into the next.
- **`FAKE_KEY = {} as CryptoKey` used with real `sign`** — if `sign` is not also spied,
  passing a fake object causes a `DOMException: Invalid key`. Mock both `importKey` and
  `sign` together.

## Gotchas

- `vi.spyOn` wraps the method on `crypto.subtle` and stores the original. Because
  `SubtleCrypto` methods are non-enumerable and non-configurable in some V8 builds, verify
  the spy was installed by asserting `vi.isMockFunction(crypto.subtle.digest)` before the
  test logic runs.
- `ArrayBuffer` instances are not `===`-comparable. Use
  `expect(new Uint8Array(result)).toEqual(new Uint8Array(FIXED_DIGEST))` to assert on
  digest output bytes, not `toEqual(FIXED_DIGEST)` on the buffer itself.
- The Workers compatibility flag `"web_crypto_module"` (if enabled) replaces the default
  subtle implementation. Spies still work but the replaced implementation may throw on
  certain algorithm names that BoringSSL supports but the compatibility shim does not.

## Verification

```bash
# Run only crypto tests with verbose output
pnpm vitest run src/hmac.test.ts --reporter=verbose

# Confirm spies are being installed (no "not a function" errors)
pnpm vitest run --reporter=verbose 2>&1 | grep -E '(PASS|FAIL|crypto)'

# Check no real network/crypto entropy leaks in CI timings
pnpm vitest run --reporter=json | jq '.testResults[].assertionResults[].duration'
```

## Related

- `vitest-workers-environment-custom-fetch-mock.md`
- `vitest-workers-miniflare-testing-setup.md`
- `vitest-pool-workers-cloudflare-test-api.md`
- `typescript-cloudflare-workers-strict.md`

## Sources

- Web Crypto API (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto
- Cloudflare Workers Web Crypto — https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- Vitest `vi.spyOn` docs — https://vitest.dev/api/vi.html#vi-spyon
- RFC 4231 HMAC-SHA test vectors — https://www.rfc-editor.org/rfc/rfc4231
- `@cloudflare/vitest-pool-workers` — https://developers.cloudflare.com/workers/testing/vitest-integration/
