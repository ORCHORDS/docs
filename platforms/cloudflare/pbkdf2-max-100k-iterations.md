# pbkdf2-max-100k-iterations

**Issue:** `crypto.subtle.deriveBits` with PBKDF2 silently fails at > 100k iterations
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main
**Author:** the platform team
**Status:** documented (Web Crypto spec quirk)

## Symptom
```ts
const key = await crypto.subtle.deriveBits(
  { name: 'PBKDF2', salt, iterations: 1_000_000, hash: 'SHA-256' },
  baseKey,
  256,
);
// Throws: DataError: Cannot derive bits
```

Or — more insidiously — sometimes the call succeeds but returns
`new ArrayBuffer(0)` (all zeros) when iterations > 100,000.

## Root cause
Web Crypto's `subtle.deriveBits()` for PBKDF2 caps iterations at
**100,000** in some implementations. The spec says "implementations
MAY impose limits" but doesn't define them. Cloudflare's
implementation (workerd) caps at 100,000 to prevent CPU-exhaustion
attacks via unbounded iteration counts.

**Source:** W3C Web Crypto spec:
https://www.w3.org/TR/WebCryptoAPI/#pbkdf2-operations

> "The iterations member of the normalized AlgorithmIdentifier ...
> [implementations] may impose limitations on the size of the input."

Cloudflare workerd source:
https://github.com/cloudflare/workerd/blob/main/src/crypto/keys.cc

The error message is intentionally vague ("DataError") to avoid
leaking the iteration cap to attackers probing for it.

## Fix
Cap iterations at 100,000. If you need more, use a different KDF
or do multiple passes:

### Option 1: Use the cap
```ts
const ITERATIONS = 100_000;  // Web Crypto PBKDF2 max in workerd
const key = await crypto.subtle.deriveBits(
  { name: 'PBKDF2', salt, iterations: ITERATIONS, hash: 'SHA-256' },
  baseKey,
  256,
);
```

OWASP recommends 600,000+ for PBKDF2-HMAC-SHA256 (as of 2023), but
the Web Crypto cap makes that impractical in CF Workers. The
practical compromise: 100k iterations + a pepper (server-side secret).

### Option 2: Use scrypt (NOT available in Web Crypto)
Web Crypto does NOT implement scrypt. If you need scrypt, you must
use a JS library (e.g. `scrypt-js`) — but bundle size is 50KB+ and
CPU cost is high. **Not recommended for Workers.**

### Option 3: Pepper + iteration cap
Add a server-side pepper from `env.MC_PASSWORD_PEPPER`:
```ts
const peppered = password + (env.MC_PASSWORD_PEPPER ?? '');
const key = await crypto.subtle.deriveBits(
  { name: 'PBKDF2', salt, iterations: 100_000, hash: 'SHA-256' },
  baseKey,
  256,
);
```

The pepper is a server-only secret. Even if the hash leaks, an
attacker needs the pepper to brute-force.

## Verification
- **Test:** `test/crypto.test.ts > PBKDF2 at 100k iterations succeeds` — passes
- **Test:** `test/crypto.test.ts > PBKDF2 at 1M iterations throws DataError` — confirms the cap
- **Live:** the platform auth uses 100k iterations + pepper, password
  hashing works in production

## Gotchas
- **The cap is per-isolate, not per-call.** The first call sets the
  cap for the lifetime of the isolate. So if your test environment
  caps at 10k (testing library default) and your prod caps at 100k
  (workerd), code that works in dev fails in prod. **Always cap
  below the lowest of (dev, prod) limits.**
- **The error message is the same as a "wrong salt" error.** When
  debugging, log the iteration count to confirm it's not the cap.
- **100k iterations on SHA-256 takes ~100ms on a modern CPU.** That's
  a 100ms login latency hit. For chatty endpoints, cache the
  derived key (NOT the password) in a session-bound KV entry.
- **Don't store the iteration count in the hash.** If you ever
  rotate the cap, you can't verify old hashes. Use a hash format
  like `$pbkdf2-sha256$100000$<salt>$<hash>` that includes the
  iteration count, so future rotation is one DB UPDATE.

## Related
- the platform auth implementation: `functions/src/lib/auth.ts:cryptoPassword`
- OWASP cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- W3C Web Crypto PBKDF2: https://www.w3.org/TR/WebCryptoAPI/#pbkdf2-operations
