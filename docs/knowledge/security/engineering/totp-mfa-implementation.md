# totp-mfa-implementation

**Issue:** RFC 6238 TOTP MFA — generation, verification, recovery
**Date:** 2026-08-09
**Status:** documented

## Symptom
You add TOTP MFA. A user enrolls. They enter the 6-digit code from
their authenticator app. You reject it. They try again 30 seconds
later. Accepted. Theyre confused.

## Root cause
TOTP (Time-based One-Time Password) per RFC 6238 has a 30-second
window by default. The clock on the server and the clock on the
user's phone can drift by seconds. If you only check the current
window, even 1 second of drift = mismatch.

**Source:** RFC 6238:
https://datatracker.ietf.org/doc/html/rfc6238

> "We recommend that the verification step allows a window of at
> least ±1 time step."

## Fix
The TOTP algorithm:

```ts
// Generate a 6-digit code from a base32 secret + current time
import { TOTP, Secret } from 'otpauth';

const secret = new Secret({ size: 20 });  // 160 bits, RFC 4226 §4 R1
const totp = new TOTP({
  issuer: 'The Platform',
  label: user.email,
  algorithm: 'SHA1',  // RFC 6238 default; SHA256 also OK
  digits: 6,
  period: 30,
  secret,
});

// Encode for QR code (otpauth:// URI)
const uri = totp.toString();  // otpauth://totp/...
```

### Verification (server side)
Check the current window AND ±1 window (for clock drift):

```ts
function verifyTotp(secret: string, code: string): boolean {
  const totp = new TOTP({ secret: <redacted-secret> digits: 6, period: 30 });
  const now = Date.now();
  // Check current, previous, and next windows
  for (let skew = -1; skew <= 1; skew++) {
    const windowTime = now + skew * 30_000;
    if (totp.generate({ timestamp: windowTime }) === code) {
      return true;
    }
  }
  return false;
}
```

This tolerates ±30 seconds of clock drift, which covers 99% of
real-world cases.

### Prevent replay
The same code shouldn't be accepted twice. Track the last
accepted counter:

```ts
async function verifyAndConsume(secret: string, code: string, lastCounter: number): Promise<boolean> {
  const totp = new TOTP({ secret: <redacted-secret> digits: 6, period: 30 });
  const now = Date.now();
  for (let skew = -1; skew <= 1; skew++) {
    const windowTime = now + skew * 30_000;
    const windowCounter = Math.floor(windowTime / 30_000);
    if (windowCounter > lastCounter && totp.generate({ timestamp: windowTime }) === code) {
      // Update lastCounter in DB
      return true;
    }
  }
  return false;
}
```

## Recovery codes
TOTP without a recovery path is a UX trap. Generate 10
single-use recovery codes at enrollment:

```ts
const RECOVERY_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
function generateRecoveryCode(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(10));
  let code = '';
  for (const b of bytes) code += RECOVERY_ALPHABET[b % RECOVERY_ALPHABET.length];
  return code.slice(0, 5) + '-' + code.slice(5);  // XXXXX-XXXXX
}

const recoveryCodes = Array.from({ length: 10 }, generateRecoveryCode);
const recoveryHashes = await Promise.all(
  recoveryCodes.map(c => hashPassword(c))
);
// Store recoveryHashes in DB; show recoveryCodes to user ONCE
```

Each recovery code is consumed (deleted) on use. The user can
regenerate the list (invalidating the old) at any time.

## Verification
- **Test:** `test/totp.test.ts` — enroll, generate, verify, replay
  attack rejected, recovery codes work
- **Live:** Authy / Google Authenticator / 1Password all generate
  compatible codes
- **Skew test:** Manually set server clock ±60s, verify still works
  for ±1 window (rejects at ±2 windows)

## Gotchas
- **Base32 secret encoding is case-insensitive** and ignores
  padding. `JBSWY3DPEHPK3PXP` and `jbswy3dpehpk3pxp` are the same.
- **Use 160-bit (20-byte) secrets** per RFC 4226 §4 R1. Shorter
  secrets are brute-forceable.
- **The secret in the QR code is the user's credential.** Treat it
  like a password — never log it, never send it to analytics, never
  display it after enrollment.
- **Time-based, not counter-based.** Don't use HOTP (counter-based)
  for user MFA — the user has to manually advance the counter, and
  they won't.
- **Rate-limit TOTP verification attempts** (5 wrong codes = 30s
  cooldown). Otherwise a stolen phone + guessed 6-digit code = bypass.
- **Recovery codes need the same protection as passwords** —
  hashed, single-use, regeneratable.

## Related
- `webauthn-passkey-flow.md` (modern alternative)
- `pbkdf2-max-100k-iterations.md` (for hashing recovery codes)
- RFC 6238: https://datatracker.ietf.org/doc/html/rfc6238
- RFC 4226: https://datatracker.ietf.org/doc/html/rfc4226
- otpauth library: https://github.com/hectorm/otpauth
