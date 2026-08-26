# webauthn-passkey-flow

**Issue:** WebAuthn registration + assertion flow gotchas
**Date:** 2026-08-09
**Status:** documented

## Symptom
You implement WebAuthn passkeys. The user registers a passkey in
Chrome on Mac. They log in from Safari on iOS. The login fails with
"NotAllowedError". The passkey doesn't sync.

## Root cause
WebAuthn has multiple attestation types, RP ID requirements, and
authenticator transport hints. Common pitfalls:
- **RP ID mismatch.** The Relying Party ID (RP ID) must be a
  registrable domain suffix of the origin. If you set RP ID =
  `example.com` but the page loads from `www.example.com`, the
  assertion fails. If you set RP ID = `example.com` and the user is
  on `staging.example.com`, the assertion fails.
- **User verification (UV) flag.** If you require UV (biometric /
  PIN), the authenticator must support it. iCloud Keychain supports
  UV; many hardware keys don't.
- **Attestation type.** `direct` requires the authenticator to
  return attestation; `none` skips it. For 21+ social platforms,
  `none` is usually fine (you trust the browser's UX).
- **Cross-device passkeys.** The credential might be on the user's
  iPhone but they're trying to log in on their Mac. The
  `hybrid` transport (Bluetooth / QR) is needed.

**Source:** W3C WebAuthn spec:
https://w3c.github.io/webauthn/

> "The RP ID ... must be equal to the origin's effective domain or
> a registrable domain suffix of the origin's effective domain."

## Fix
A complete passkey flow has 4 steps:

### 1. Registration challenge
```ts
// Server: generate challenge, send to client
const challenge = crypto.getRandomValues(new Uint8Array(32));
const userId = await getOrCreateUser(email);
const options: PublicKeyCredentialCreationOptions = {
  challenge,
  rp: { name: 'The Platform', id: 'example.com' },  // NO protocol, NO port
  user: {
    id: new TextEncoder().encode(userId),
    name: email,
    displayName: email,
  },
  pubKeyCredParams: [
    { alg: -7, type: 'public-key' },   // ES256
    { alg: -257, type: 'public-key' }, // RS256
  ],
  authenticatorSelection: {
    residentKey: 'preferred',
    userVerification: 'preferred',  // not 'required' — fall back to PIN
  },
  timeout: 60000,
  attestation: 'none',  // we trust the browser
};
```

### 2. Client registration
```ts
// Browser: navigator.credentials.create
const credential = await navigator.credentials.create({
  publicKey: options,
});
// POST credential to /api/auth/passkey/register
```

### 3. Server registration verification
```ts
// Verify the attestation
const clientDataJSON = JSON.parse(
  new TextDecoder().decode(credential.response.clientDataJSON)
);
// Verify: clientDataJSON.type === 'webauthn.create'
// Verify: clientDataJSON.challenge === btoa(challenge)
// Verify: clientDataJSON.origin === 'https://example.com'

// Store credential.id + credential.publicKey in `passkeys` table
await env.DB.prepare(
  `INSERT INTO passkeys (id, user_id, public_key, counter, transports, created_at)
   VALUES (?, ?, ?, ?, ?, ?)`
).bind(credential.id, userId, credential.response.getPublicKey(),
       credential.response.attestationObject.counter, ...);
```

### 4. Login assertion
Same flow but with `navigator.credentials.get()`. Verify the
signature using the stored public key. Increment the counter on
each use (replay protection).

## Verification
- **Test:** `test/passkey.test.ts` — register + assert round-trip
  with vitest + simulated authenticator
- **Live:** Test in Chrome + Safari + Firefox + iOS Safari
- **Authenticator:** Test with Touch ID, Face ID, Windows Hello,
  hardware key (YubiKey), and iCloud Keychain sync

## Gotchas
- **RP ID = eTLD+1.** Set it to `example.com` (no `www.`, no
  `https://`). The browser appends the rest.
- **The challenge MUST be cryptographically random** (32 bytes
  from `crypto.getRandomValues`). Predictable challenges = bypass.
- **`userVerification: 'preferred'` is the right default.** It
  falls back to device PIN if biometric is unavailable. Don't use
  `'required'` unless you have a reason.
- **Counter must increment.** If the new counter <= old counter,
  the credential was cloned. Reject the assertion.
- **Passkey sync (iCloud Keychain, Google Password Manager) is
  opt-in.** Some users don't have it enabled. Fall back to TOTP.
- **Cross-device login** (laptop → phone) needs `hybrid` transport
  hint. The browser will show a QR code for the phone.

## Related
- `totp-mfa-implementation.md` (fallback for non-passkey users)
- W3C WebAuthn: https://w3c.github.io/webauthn/
- MDN: https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API
