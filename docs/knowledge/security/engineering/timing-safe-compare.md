# timing-safe-compare

**Issue:** String equality comparison for secrets leaks timing information — use constant-time compare
**Date:** 2026-08-11
**Status:** documented

## Symptom

Comparing a bearer token or password hash with `===` allows a timing oracle attack.
An attacker can determine how many characters of their guess are correct by measuring
response time — the comparison short-circuits on the first mismatch.

## The fix — Workers (no Node.js crypto)

Cloudflare Workers has `crypto.subtle` but NOT Node's `timingSafeEqual`. Use a
HMAC-based constant-time comparison:

```typescript
async function timingSafeEqual(a: string, b: string): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode('timingsafe'),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const [sigA, sigB] = await Promise.all([
    crypto.subtle.sign('HMAC', key, new TextEncoder().encode(a)),
    crypto.subtle.sign('HMAC', key, new TextEncoder().encode(b)),
  ]);
  // ArrayBuffer equality — still constant-time because both have same length:
  const bytesA = new Uint8Array(sigA);
  const bytesB = new Uint8Array(sigB);
  if (bytesA.length !== bytesB.length) return false;
  let diff = 0;
  for (let i = 0; i < bytesA.length; i++) diff |= bytesA[i] ^ bytesB[i];
  return diff === 0;
}
```

Why this works: HMAC output is always 32 bytes regardless of input. Comparing
two equal-length buffers bit-by-bit in a single loop is constant-time.

## Usage

```typescript
// Comparing bearer tokens (SCIM, webhook secrets):
const stored = await env.DB!.prepare(`SELECT token FROM api_keys WHERE id = ?`).bind(id).first<{token: string}>();
if (!stored || !(await timingSafeEqual(stored.token, incoming))) {
  return jsonError(401, 'unauthorized', undefined, undefined);
}

// Comparing HMAC webhook signatures (Stripe, GitHub, etc.):
const computed = await computeHmacHex(payload, env.WEBHOOK_SECRET!);
if (!(await timingSafeEqual(computed, incomingSignature))) {
  return jsonError(401, 'invalid_signature', undefined, undefined);
}
```

## What NOT to do

```typescript
// Wrong — vulnerable to timing oracle:
if (token === stored.token) { ... }

// Wrong — .includes() is also timing-vulnerable:
if (stored.token.includes(token)) { ... }

// Wrong — byte-by-byte with early return:
for (let i = 0; i < a.length; i++) {
  if (a[i] !== b[i]) return false;  // early return leaks position of mismatch
}
```

## HMAC signature verification for webhooks

```typescript
async function verifyWebhookSignature(
  payload: string,
  signature: string,
  secret: string,
): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const mac = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload));
  const computed = Array.from(new Uint8Array(mac))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
  // signature may have 'sha256=' prefix (GitHub format):
  const incoming = signature.replace(/^sha256=/, '');
  return timingSafeEqual(computed, incoming);
}
```

## Password hashing

Do NOT store passwords as plain text or compare with timingSafeEqual. Use a proper
password hashing algorithm. Workers doesn't have bcrypt, but can call an external
KV/R2-backed hash verification service, or use PBKDF2 via crypto.subtle:

```typescript
async function hashPassword(password: string, salt: Uint8Array): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(password),
    'PBKDF2',
    false,
    ['deriveBits'],
  );
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt, iterations: 310_000, hash: 'SHA-256' },
    key,
    256,
  );
  const hashArray = new Uint8Array(bits);
  return `pbkdf2:${Buffer.from(salt).toString('base64')}:${Buffer.from(hashArray).toString('base64')}`;
}
```

## Gotchas

- **Length check BEFORE bit-by-bit compare**: If lengths differ, you know the strings are different, but revealing this is itself a timing oracle when length is secret. For fixed-length tokens (UUIDs, HMACs), length is public. For variable-length passwords, hash first — hashes are fixed-length.
- **Async overhead**: `timingSafeEqual` using HMAC adds ~0.5ms vs direct `===`. Acceptable for auth paths; not for hot loops.
- **Don't trust `===` even for HMAC outputs**: Two hex strings of the same length are still timing-vulnerable with `===` due to JS engine optimizations. Always use the loop.
- **SCIM token two-step**: See `scim-bearer-token-auth.md` — even after SQL equality check, do a timingSafeEqual re-verify.

## Related

- `scim-bearer-token-auth.md`
- `saml-sp-workers.md`
- `mccontext-gate-pattern.md`
- `webhook-handler-pattern.md`
