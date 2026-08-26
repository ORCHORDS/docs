# Mobile Biometric Authentication with Workers WebAuthn Credential Storage

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You want users of example project (example.com) to register a passkey on their phone using Face ID or fingerprint, then log in on any device without a password. The credential public key must be stored server-side in a Cloudflare-managed store (Workers KV or D1) and the authentication ceremony must run inside a Cloudflare Worker — without any origin server.

## Context

WebAuthn (FIDO2) splits registration and authentication into two round-trip ceremonies. The **relying party** (RP) logic — challenge issuance, credential storage, assertion verification — normally lives on a server. Cloudflare Workers can host the full RP in a zero-infrastructure deployment. On mobile:

- **iOS**: `ASAuthorizationController` (AuthenticationServices) handles platform authenticators (Face ID / Touch ID) and iCloud Keychain sync passkeys.
- **Android**: Credential Manager API (`androidx.credentials`) handles both platform biometrics and FIDO2 roaming authenticators.
- **React Native / Expo**: `react-native-passkey` (iOS 16+, Android API 28+) or a WebView-based fallback wrapping the Web Authentication API in WKWebView / Chrome Custom Tab.

The Cloudflare Worker plays the role of the RP server: it issues challenges stored in KV (TTL 5 minutes), verifies CBOR-encoded attestation/assertion objects, and persists `credentialId → publicKey` mappings in D1.

---

## 1. Worker: Challenge Issuance and Storage

```ts
// workers/webauthn/src/index.ts
import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { uint8ToBase64url, base64urlToUint8 } from './encoding'

const app = new Hono<{ Bindings: Env }>()
app.use('*', cors({ origin: ['https://example.com'], credentials: true }))

// POST /webauthn/register/begin
app.post('/webauthn/register/begin', async (c) => {
  const { userId, username } = await c.req.json<{ userId: string; username: string }>()

  const challenge = crypto.getRandomValues(new Uint8Array(32))
  const challengeB64 = uint8ToBase64url(challenge)

  // Store challenge keyed by userId, TTL 5 min
  await c.env.WEBAUTHN_KV.put(
    `challenge:reg:${userId}`,
    challengeB64,
    { expirationTtl: 300 }
  )

  return c.json({
    challenge: challengeB64,
    rp: { id: 'example.com', name: 'example project' },
    user: {
      id: uint8ToBase64url(new TextEncoder().encode(userId)),
      name: username,
      displayName: username,
    },
    pubKeyCredParams: [
      { alg: -7, type: 'public-key' },   // ES256
      { alg: -257, type: 'public-key' }, // RS256 fallback
    ],
    authenticatorSelection: {
      residentKey: 'required',
      userVerification: 'required',
    },
    timeout: 60000,
    attestation: 'none', // 'direct' if you need device attestation
  })
})

export default app
```

---

## 2. Worker: Registration Completion and D1 Persistence

```ts
import { verifyRegistrationResponse } from '@simplewebauthn/server'

// POST /webauthn/register/complete
app.post('/webauthn/register/complete', async (c) => {
  const { userId, credential } = await c.req.json<{
    userId: string
    credential: RegistrationResponseJSON
  }>()

  const storedChallenge = await c.env.WEBAUTHN_KV.get(`challenge:reg:${userId}`)
  if (!storedChallenge) return c.json({ error: 'Challenge expired' }, 400)

  let verification
  try {
    verification = await verifyRegistrationResponse({
      response: credential,
      expectedChallenge: storedChallenge,
      expectedOrigin: 'https://example.com',
      expectedRPID: 'example.com',
      requireUserVerification: true,
    })
  } catch (e) {
    return c.json({ error: 'Verification failed', detail: String(e) }, 400)
  }

  if (!verification.verified || !verification.registrationInfo) {
    return c.json({ error: 'Not verified' }, 400)
  }

  const { credentialID, credentialPublicKey, counter } = verification.registrationInfo

  // Persist to D1
  await c.env.DB.prepare(
    `INSERT INTO webauthn_credentials
       (credential_id, user_id, public_key, counter, created_at)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(
    uint8ToBase64url(credentialID),
    userId,
    uint8ToBase64url(credentialPublicKey),
    counter,
    new Date().toISOString()
  ).run()

  // Invalidate challenge
  await c.env.WEBAUTHN_KV.delete(`challenge:reg:${userId}`)

  return c.json({ verified: true })
})
```

D1 schema:

```sql
CREATE TABLE webauthn_credentials (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  credential_id TEXT    NOT NULL UNIQUE,
  user_id       TEXT    NOT NULL,
  public_key    TEXT    NOT NULL,
  counter       INTEGER NOT NULL DEFAULT 0,
  aaguid        TEXT,
  created_at    TEXT    NOT NULL
);
CREATE INDEX idx_cred_user ON webauthn_credentials(user_id);
```

---

## 3. React Native Registration Flow

```tsx
// src/auth/usePasskeyRegistration.ts
import { Passkey } from 'react-native-passkey'
import type { PasskeyRegistrationRequest } from 'react-native-passkey'

export async function registerPasskey(userId: string, username: string) {
  // 1. Fetch challenge from Worker
  const beginRes = await fetch('https://api.example.com/webauthn/register/begin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, username }),
  })
  const options = await beginRes.json()

  // 2. Invoke platform authenticator
  let credential
  try {
    credential = await Passkey.register(options as PasskeyRegistrationRequest)
  } catch (err: any) {
    if (err.message?.includes('UserCancelled')) throw new Error('Cancelled')
    if (err.message?.includes('NotSupported')) throw new Error('Passkeys not supported on this device')
    throw err
  }

  // 3. Send attestation to Worker
  const completeRes = await fetch('https://api.example.com/webauthn/register/complete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, credential }),
  })
  const result = await completeRes.json()
  if (!result.verified) throw new Error('Server rejected registration')
  return result
}
```

---

## 4. Authentication Ceremony

```ts
// Worker: POST /webauthn/auth/begin
app.post('/webauthn/auth/begin', async (c) => {
  const { userId } = await c.req.json<{ userId: string }>()

  const creds = await c.env.DB.prepare(
    'SELECT credential_id FROM webauthn_credentials WHERE user_id = ?'
  ).bind(userId).all()

  const challenge = uint8ToBase64url(crypto.getRandomValues(new Uint8Array(32)))
  await c.env.WEBAUTHN_KV.put(`challenge:auth:${userId}`, challenge, { expirationTtl: 300 })

  return c.json({
    challenge,
    rpId: 'example.com',
    userVerification: 'required',
    allowCredentials: creds.results.map((r: any) => ({
      id: r.credential_id,
      type: 'public-key',
      transports: ['internal', 'hybrid'],
    })),
    timeout: 60000,
  })
})

// Worker: POST /webauthn/auth/complete
app.post('/webauthn/auth/complete', async (c) => {
  const { userId, assertion } = await c.req.json()
  const storedChallenge = await c.env.WEBAUTHN_KV.get(`challenge:auth:${userId}`)
  if (!storedChallenge) return c.json({ error: 'Challenge expired' }, 400)

  const cred = await c.env.DB.prepare(
    'SELECT public_key, counter FROM webauthn_credentials WHERE credential_id = ?'
  ).bind(assertion.id).first()

  if (!cred) return c.json({ error: 'Unknown credential' }, 400)

  const { verifyAuthenticationResponse } = await import('@simplewebauthn/server')
  const verification = await verifyAuthenticationResponse({
    response: assertion,
    expectedChallenge: storedChallenge,
    expectedOrigin: 'https://example.com',
    expectedRPID: 'example.com',
    authenticator: {
      credentialID: base64urlToUint8(assertion.id),
      credentialPublicKey: base64urlToUint8(cred.public_key as string),
      counter: cred.counter as number,
    },
    requireUserVerification: true,
  })

  if (verification.verified) {
    // Update counter to prevent replay
    await c.env.DB.prepare(
      'UPDATE webauthn_credentials SET counter = ? WHERE credential_id = ?'
    ).bind(verification.authenticationInfo.newCounter, assertion.id).run()

    await c.env.WEBAUTHN_KV.delete(`challenge:auth:${userId}`)

    // Issue your JWT/session cookie here
    return c.json({ verified: true })
  }

  return c.json({ error: 'Authentication failed' }, 401)
})
```

---

## Anti-patterns

- **Storing challenges in D1 instead of KV** — D1 has higher write latency and no built-in TTL; KV with `expirationTtl` is the correct store for ephemeral challenges.
- **Skipping counter validation** — the `counter` field prevents credential cloning; failing to update it after each assertion allows replay attacks.
- **Using `attestation: 'direct'` without verifying AAGUID** — direct attestation forces Apple / Google device certificate chains which break on older devices; use `'none'` unless you have a specific enterprise need.
- **Setting `userVerification: 'preferred'` instead of `'required'`** — on mobile this silently downgrades to PIN-only on some Android devices, bypassing biometric.
- **Single `rpId` for both web and native** — `react-native-passkey` uses the `rpId` to match against the app's associated domain; your `.well-known/apple-app-site-association` and `assetlinks.json` must list the app's identifier.

---

## Gotchas

- **iCloud Keychain sync latency**: after registration on iPhone A, the passkey may not be immediately available on iPhone B. Add a "use a different method" fallback.
- **Android API level gating**: `androidx.credentials.CredentialManager` requires API 28+. `react-native-passkey` throws `NotSupported` on lower levels — handle this gracefully and fall back to JWT + biometric local key unlock.
- **Workers `@simplewebauthn/server` bundle size**: the CBOR parser used by the library is large. Use `wrangler build --minify` and check that the compressed bundle stays under the 3 MB Worker script limit.
- **`rpId` must match the eTLD+1**: using a subdomain (e.g., `api.example.com`) as `rpId` causes credential registration to fail on iOS. Always set `rpId: 'example.com'`.
- **Cross-origin iframes in WKWebView**: WebAuthn ceremonies inside a WKWebView that points to a cross-origin page fail silently on iOS 15 and earlier; users must be on iOS 16+ for `create()` / `get()` to work inside a WebView context.

---

## Verification

```bash
# Confirm D1 credentials table is populated after registration
wrangler d1 execute example project_DB --command \
  "SELECT credential_id, user_id, counter FROM webauthn_credentials LIMIT 5;"

# Confirm KV challenge was cleaned up
wrangler kv key list --namespace-id $WEBAUTHN_KV_ID | grep challenge

# Simulate authentication ceremony end-to-end
curl -X POST https://api.example.com/webauthn/auth/begin \
  -H "Content-Type: application/json" \
  -d '{"userId":"test-user-1"}' | jq .

# Confirm counter incremented after assertion
wrangler d1 execute example project_DB --command \
  "SELECT counter FROM webauthn_credentials WHERE user_id = 'test-user-1';"
```

---

## Related

- `biometric-auth.md` — local biometric key unlock (device-bound, no passkey sync)
- `react-native-biometric-auth.md` — `react-native-biometrics` for TouchID/FaceID local auth
- `mobile-jwt-storage-pitfalls.md` — secure token storage after WebAuthn authentication
- `ios-keychain-storage.md` — storing session tokens post-passkey login
- `android-credential-manager-passkey-migration.md` — migration from FIDO2 library to Credential Manager

---

## Sources

- [W3C WebAuthn Level 3 specification](https://www.w3.org/TR/webauthn-3/)
- [SimpleWebAuthn server library](https://simplewebauthn.dev/)
- [react-native-passkey on GitHub](https://github.com/f-23/react-native-passkey)
- [Apple AuthenticationServices (ASAuthorizationController)](https://developer.apple.com/documentation/authenticationservices)
- [Android Credential Manager passkey guide](https://developer.android.com/training/sign-in/passkeys)
- [Cloudflare Workers KV TTL documentation](https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys)
