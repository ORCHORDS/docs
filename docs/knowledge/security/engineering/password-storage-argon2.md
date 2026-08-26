# password-storage-argon2

**Issue:** Password hashing — Argon2id, bcrypt, scrypt
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user signs up with password "password123". Your code
hashes it with SHA-256. You store
`5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8`.
A security breach exposes the DB. The attacker cracks
SHA-256 with rainbow tables in seconds. 10M passwords are
compromised.

## Root cause
**SHA-256 is not a password hash.** It's a fast hash; an
attacker can try billions per second.

**Source:** OWASP — Password Storage:
https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html

> "Passwords should be stored using a password hashing
> algorithm that is computationally expensive. ... SHA-256
> is NOT suitable for password storage."

## The "Argon2id" choice

Argon2id is the modern standard:
- **Winner** of the 2015 Password Hashing Competition
- **Memory-hard** (resists GPU attacks)
- **Configurable** (memory, time, parallelism)

```ts
import { hash, verify, Algorithm } from '@node-rs/argon2';

const hashed = await hash(password, {
  algorithm: Algorithm.Argon2id,
  memoryCost: 19456,  // 19 MB (minimum for OWASP)
  timeCost: 2,         // 2 iterations
  parallelism: 1,
});
```

The output includes the salt + parameters; the verify
function reads them.

## The "verify" pattern

```ts
import { verify } from '@node-rs/argon2';

const isValid = await verify(hashedPassword, userInputPassword);
```

The verify function:
- Extracts the salt from the hash
- Hashes the user input with the same salt + parameters
- Compares in constant time

## The "bcrypt" alternative

If Argon2id is not available, use bcrypt:
```ts
import { hash, compare } from 'bcryptjs';

const hashed = await hash(password, 12);  // 12 rounds
const isValid = await compare(userInputPassword, hashed);
```

Bcrypt is well-supported; Argon2id is preferred.

## The "scrypt" alternative

If neither is available, use scrypt:
```ts
import { scrypt, randomBytes, timingSafeEqual } from 'crypto';
import { promisify } from 'util';

const scryptAsync = promisify(scrypt);

async function hash(password: string): Promise<string> {
  const salt = randomBytes(16).toString('hex');
  const buf = (await scryptAsync(password, salt, 64)) as Buffer;
  return `${salt}:${buf.toString('hex')}`;
}

async function verify(password: string, hashed: string): Promise<boolean> {
  const [salt, hashHex] = hashed.split(':');
  const buf = (await scryptAsync(password, salt, 64)) as Buffer;
  return timingSafeEqual(buf, Buffer.from(hashHex, 'hex'));
}
```

Scrypt is memory-hard; bcrypt is not.

## The "DO NOT" list

❌ **MD5:** Broken; instant to crack
❌ **SHA-1:** Broken; instant to crack
❌ **SHA-256:** Too fast; GPU-crackable
❌ **SHA-3:** Same problem as SHA-256
❌ **Bcrypt with rounds < 10:** Too fast
❌ **Custom hash function:** Almost always broken
❌ **Reversible encryption:** Wrong tool; use a hash
❌ **Plain text:** Catastrophic

## The "salt" pattern

A salt makes rainbow tables useless:
```ts
// Argon2id includes the salt in the output
const hashed = await hash(password);
// Output: $argon2id$v=19$m=19456,t=2,p=1$randomsalt$hash
```

The salt is per-user; an attacker must crack each password
individually.

## The "parameters" choice

For Argon2id, OWASP recommends:
- **Memory:** 19 MB (or as much as you can afford)
- **Time:** 2 iterations
- **Parallelism:** 1

The parameters control the trade-off between security
and CPU cost.

## The "rehash on login" pattern

If you increase the parameters, rehash on login:
```ts
async function verifyAndMaybeRehash(password: string, hashed: string): Promise<string> {
  const isValid = await verify(hashed, password);
  if (!isValid) throw new Error('Invalid');

  // Check if the parameters are below current standard
  const params = parseHashedParams(hashed);  // Custom: parse the hash format
  if (isBelowStandard(params)) {
    return hash(password, CURRENT_PARAMS);  // Rehash with new params
  }

  return hashed;
}

// Usage
const user = await getUser(email, env);
const newHash = await verifyAndMaybeRehash(inputPassword, user.password_hash);
if (newHash !== user.password_hash) {
  await updateUserPassword(user.id, newHash, env);
}
```

The user's password is rehashed with the new parameters
on next login.

## The "timing-safe compare" pattern

For comparing hashes, use a constant-time compare:
```ts
import { timingSafeEqual } from 'crypto';

function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  return timingSafeEqual(Buffer.from(a), Buffer.from(b));
}
```

A non-constant-time compare leaks the comparison time;
the attacker can use this to guess the hash.

## The "rate limit" pattern

For login attempts, rate limit:
```ts
async function checkLoginAttempts(email: string, env: Env): Promise<{ allowed: boolean; remaining: number }> {
  // ... see rate-limiting patterns
}
```

Brute force is blocked.

## The "breach detection" pattern

For checking passwords against known breaches:
```ts
async function isPasswordBreached(password: string): Promise<boolean> {
  const sha1 = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(password));
  const hash = Array.from(new Uint8Array(sha1)).map(b => b.toString(16).padStart(2, '0')).join('').toUpperCase();
  const prefix = hash.slice(0, 5);
  const suffix = hash.slice(5);

  const response = await fetch(`https://api.pwnedpasswords.com/range/${prefix}`);
  const text = await response.text();

  return text.split('\n').some((line) => line.startsWith(suffix));
}
```

The HIBP API is the standard for breach detection.

## The "password rotation" pattern

For sensitive apps, require password rotation:
```ts
async function isPasswordExpired(user: User): Promise<boolean> {
  const maxAge = 90 * 24 * 60 * 60 * 1000;  // 90 days
  return Date.now() - new Date(user.password_updated_at).getTime() > maxAge;
}
```

NIST 800-63B no longer recommends forced rotation; do it
for high-security apps only.

## The "Argon2id libraries" choice

For Node.js / CF Workers:
- **`@node-rs/argon2`:** Native; fast
- **`argon2`:** Native; well-maintained
- **`argon2-browser`:** Browser (for client-side hashing)

For other languages:
- **Python:** `argon2-cffi`
- **Go:** `golang.org/x/crypto/argon2`
- **Java:** `de.mkammerer:argon2-jvm`
- **PHP:** `paragonie/argon2-php`

## The "password upgrade" pattern

If you have legacy SHA-256 hashes, upgrade on next login:
```ts
async function verifyLegacyAndUpgrade(password: string, user: User, env: Env): Promise<boolean> {
  // 1. Try the legacy hash
  const legacyHash = sha256(password);
  if (legacyHash === user.password_hash) {
    // 2. Upgrade to Argon2id
    const newHash = await hash(password, CURRENT_PARAMS);
    await env.DB!.prepare(
      `UPDATE users SET password_hash = ?, password_algorithm = 'argon2id' WHERE id = ?`
    ).bind(newHash, user.id).run();
    return true;
  }

  // 3. Try the new hash
  return await verify(user.password_hash, password);
}
```

The legacy hashes are upgraded gradually.

## The "cost of hashing" pattern

Argon2id with 19 MB takes ~50ms on a modern CPU. For a
high-traffic app:
- **1k logins/sec × 50ms = 50 CPU-seconds/sec** = 50 cores
  needed (over-provisioning; can batch)

For most apps, this is fine. For very high traffic, use a
queue + worker for password operations.

## Verification
- **Test:** Hash is stored correctly
- **Test:** Verify works
- **Test:** Wrong password fails
- **Pen test:** Hash cracking (should be slow)
- **Audit:** Annual hash upgrade

## Gotchas
- **The "MD5/SHA-256" anti-pattern.** Always use Argon2id,
  bcrypt, or scrypt.
- **The "no salt" anti-pattern.** A saltless hash is
  rainbow-tableable.
- **The "low parameters" anti-pattern.** bcrypt with 4
  rounds is too fast; use 12+.
- **The "in-memory compare" anti-pattern.** Use
  timingSafeEqual.
- **The "no rate limit" anti-pattern.** Without rate
  limit, brute force is trivial.
- **The "long-lived password" anti-pattern.** NIST says
  no forced rotation; for high-security, rotate.

## Related
- `feature-cookbook-auth.md`
- `authentication-flows-comparison.md`
- `api-key-authentication.md`
- `totp-mfa-implementation.md`
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- Argon2: https://github.com/P-H-C/phc-winner-argon2
