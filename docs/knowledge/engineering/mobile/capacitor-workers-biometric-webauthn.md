# Capacitor Workers Biometric Authentication WebAuthn

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You have a Capacitor app that needs passwordless login using the device biometric
(Touch ID, Face ID, fingerprint) backed by a Cloudflare Workers WebAuthn ceremony.
Existing guides focus on pure-web or pure-native; Capacitor's hybrid environment
requires bridging the browser WebAuthn API with native biometric prompts and storing
credentials in the platform Keychain/Keystore via Workers.

---

## Context

WebAuthn (FIDO2) authenticates users with a public key stored on the device and
verified by a relying-party server. In Capacitor:
- On iOS the WKWebView can call `navigator.credentials.create/get` and iOS will
  present Face ID / Touch ID natively.
- On Android, the Credential Manager handles WebAuthn through the WebView.
- The Workers relying-party handles the registration and authentication ceremonies
  and stores credential public keys in D1.

Stack:
- Capacitor 6+ (iOS 17+ / Android 14+)
- `@simplewebauthn/browser` (client)
- Cloudflare Workers TypeScript + D1 + `@simplewebauthn/server`

---

## 1. Capacitor WebAuthn Client Wrapper

```typescript
// src/lib/webauthn.ts
import {
  startRegistration,
  startAuthentication,
  browserSupportsWebAuthn,
} from '@simplewebauthn/browser'

const API_BASE = 'https://api.example.com'

export async function isWebAuthnAvailable(): Promise<boolean> {
  return browserSupportsWebAuthn()
}

// --- Registration ---
export async function registerBiometric(userId: string, username: string): Promise<void> {
  const optionsResp = await fetch(`${API_BASE}/webauthn/register/options`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ userId, username }),
  })
  const options = await optionsResp.json()

  // This call triggers the native biometric prompt on iOS/Android
  const attResp = await startRegistration(options)

  const verifyResp = await fetch(`${API_BASE}/webauthn/register/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ userId, attestation: attResp }),
  })

  if (!verifyResp.ok) throw new Error('Registration verification failed')
}

// --- Authentication ---
export async function authenticateWithBiometric(): Promise<string> {
  const optionsResp = await fetch(`${API_BASE}/webauthn/auth/options`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  })
  const options = await optionsResp.json()

  // Triggers biometric prompt
  const assertResp = await startAuthentication(options)

  const verifyResp = await fetch(`${API_BASE}/webauthn/auth/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ assertion: assertResp }),
  })

  if (!verifyResp.ok) throw new Error('Authentication failed')
  const { token } = await verifyResp.json()
  return token  // JWT for subsequent API calls
}
```

---

## 2. Workers Relying-Party — Registration Ceremony

```typescript
// workers/src/webauthn-register.ts
import { Hono } from 'hono'
import { getCookie, setCookie } from 'hono/cookie'
import {
  generateRegistrationOptions,
  verifyRegistrationResponse,
} from '@simplewebauthn/server'
import type { RegistrationResponseJSON } from '@simplewebauthn/types'

interface Env {
  DB: D1Database
  CHALLENGES: KVNamespace
  RP_ID: string       // e.g. "example.com"
  RP_NAME: string     // e.g. "My App"
  ORIGIN: string      // e.g. "https://app.example.com"
}

const app = new Hono<{ Bindings: Env }>()

app.post('/webauthn/register/options', async (c) => {
  const { userId, username } = await c.req.json<{ userId: string; username: string }>()

  const existingCredentials = await c.env.DB.prepare(
    'SELECT credential_id FROM webauthn_credentials WHERE user_id = ?'
  ).bind(userId).all<{ credential_id: string }>()

  const options = await generateRegistrationOptions({
    rpName: c.env.RP_NAME,
    rpID: c.env.RP_ID,
    userID: new TextEncoder().encode(userId),
    userName: username,
    attestationType: 'none',
    excludeCredentials: existingCredentials.results.map((r) => ({
      id: r.credential_id,
      type: 'public-key' as const,
    })),
    authenticatorSelection: {
      userVerification: 'required',
      residentKey: 'preferred',
    },
  })

  // Store challenge in KV (30 second window)
  await c.env.CHALLENGES.put(`reg:${userId}`, options.challenge, { expirationTtl: 30 })

  return c.json(options)
})

app.post('/webauthn/register/verify', async (c) => {
  const { userId, attestation } = await c.req.json<{
    userId: string
    attestation: RegistrationResponseJSON
  }>()

  const expectedChallenge = await c.env.CHALLENGES.get(`reg:${userId}`)
  if (!expectedChallenge) return c.json({ error: 'challenge_expired' }, 400)

  const verification = await verifyRegistrationResponse({
    response: attestation,
    expectedChallenge,
    expectedOrigin: c.env.ORIGIN,
    expectedRPID: c.env.RP_ID,
    requireUserVerification: true,
  })

  if (!verification.verified || !verification.registrationInfo) {
    return c.json({ error: 'verification_failed' }, 400)
  }

  const { credential } = verification.registrationInfo
  await c.env.DB.prepare(
    `INSERT INTO webauthn_credentials
       (user_id, credential_id, public_key, sign_count, transports)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(
    userId,
    credential.id,
    Buffer.from(credential.publicKey).toString('base64'),
    credential.counter,
    JSON.stringify(credential.transports ?? [])
  ).run()

  await c.env.CHALLENGES.delete(`reg:${userId}`)
  return c.json({ verified: true })
})

export { app as registerApp }
```

---

## 3. Workers Relying-Party — Authentication Ceremony

```typescript
// workers/src/webauthn-auth.ts
import {
  generateAuthenticationOptions,
  verifyAuthenticationResponse,
} from '@simplewebauthn/server'
import type { AuthenticationResponseJSON } from '@simplewebauthn/types'
import { sign } from '@tsndr/cloudflare-worker-jwt'

app.post('/webauthn/auth/options', async (c) => {
  const options = await generateAuthenticationOptions({
    rpID: c.env.RP_ID,
    userVerification: 'required',
  })

  const sessionId = crypto.randomUUID()
  await c.env.CHALLENGES.put(`auth:${sessionId}`, options.challenge, { expirationTtl: 60 })
  setCookie(c, 'webauthn_session', sessionId, { httpOnly: true, sameSite: 'Strict', maxAge: 60 })

  return c.json(options)
})

app.post('/webauthn/auth/verify', async (c) => {
  const sessionId = getCookie(c, 'webauthn_session')
  if (!sessionId) return c.json({ error: 'missing_session' }, 400)

  const expectedChallenge = await c.env.CHALLENGES.get(`auth:${sessionId}`)
  if (!expectedChallenge) return c.json({ error: 'challenge_expired' }, 400)

  const { assertion } = await c.req.json<{ assertion: AuthenticationResponseJSON }>()

  const cred = await c.env.DB.prepare(
    'SELECT user_id, public_key, sign_count FROM webauthn_credentials WHERE credential_id = ?'
  ).bind(assertion.id).first<{ user_id: string; public_key: string; sign_count: number }>()

  if (!cred) return c.json({ error: 'credential_not_found' }, 404)

  const verification = await verifyAuthenticationResponse({
    response: assertion,
    expectedChallenge,
    expectedOrigin: c.env.ORIGIN,
    expectedRPID: c.env.RP_ID,
    credential: {
      id: assertion.id,
      publicKey: new Uint8Array(Buffer.from(cred.public_key, 'base64')),
      counter: cred.sign_count,
    },
    requireUserVerification: true,
  })

  if (!verification.verified) return c.json({ error: 'verification_failed' }, 401)

  // Update counter to prevent replay
  await c.env.DB.prepare(
    'UPDATE webauthn_credentials SET sign_count = ? WHERE credential_id = ?'
  ).bind(verification.authenticationInfo.newCounter, assertion.id).run()

  await c.env.CHALLENGES.delete(`auth:${sessionId}`)

  const token = await sign(
    { sub: cred.user_id, exp: Math.floor(Date.now() / 1000) + 3600 },
    c.env.JWT_SECRET
  )
  return c.json({ token })
})
```

---

## 4. D1 Credential Schema

```sql
-- workers/schema/webauthn.sql
CREATE TABLE IF NOT EXISTS webauthn_credentials (
  id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id       TEXT NOT NULL,
  credential_id TEXT NOT NULL UNIQUE,
  public_key    TEXT NOT NULL,
  sign_count    INTEGER NOT NULL DEFAULT 0,
  transports    TEXT,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wac_user     ON webauthn_credentials(user_id);
CREATE INDEX IF NOT EXISTS idx_wac_cred_id  ON webauthn_credentials(credential_id);
```

---

## 5. Capacitor — Biometric Fallback with `@capacitor-mlkit/face-detection`

```typescript
// src/lib/auth.ts
import { isWebAuthnAvailable, authenticateWithBiometric } from './webauthn'
import { NativeBiometric } from 'capacitor-native-biometric'

export async function login(): Promise<string> {
  if (await isWebAuthnAvailable()) {
    return authenticateWithBiometric()
  }
  // Fallback: native biometric gate → retrieve stored token
  const result = await NativeBiometric.verifyIdentity({
    reason: 'Confirm your identity',
    title: 'Biometric Login',
  })
  if (!result) throw new Error('Biometric verification failed')
  const { password: storedToken } = await NativeBiometric.getCredentials({
    server: 'com.example.app',
  })
  return storedToken
}
```

---

## Anti-patterns

- **Storing WebAuthn credentials in D1 without sign-count enforcement**: replay
  attacks are defeated by checking that `newCounter > storedCounter`; never skip this.
- **Using `attestationType: 'direct'`** without parsing and verifying the attestation
  statement — use `'none'` unless your threat model requires hardware attestation.
- **Sharing challenges across users**: each registration/authentication ceremony must
  have a user- or session-scoped KV key to prevent challenge substitution.
- **Not handling `NotAllowedError`**: the user may dismiss the biometric prompt; catch
  this error and offer a fallback (PIN, email OTP) rather than crashing.

---

## Gotchas

- Capacitor WKWebView on iOS requires the app's `Associated Domains` entitlement with
  `webcredentials:yourdomain.com` for WebAuthn to work; missing it causes a silent
  `NotSupportedError`.
- On Android, the WebAuthn API in Capacitor's WebView delegates to the Credential Manager
  which requires Play Services 20.0.0+; older devices fall back to FIDO2 API directly.
- `@simplewebauthn/server` requires the `crypto` global; Cloudflare Workers provide it
  natively, but do not import Node.js `crypto` in Worker code.
- RP_ID must match the effective domain of the origin exactly; mismatches produce
  `SecurityError` on the client with no useful message.

---

## Verification

```bash
# Deploy schema
wrangler d1 execute DB --remote --file workers/schema/webauthn.sql

# Check WebAuthn options endpoint
curl -c cookies.txt -X POST https://api.example.com/webauthn/auth/options \
  -H "Content-Type: application/json"

# Capacitor build check
npx cap sync ios && npx cap open ios

# Confirm Associated Domains in Xcode:
# Target → Signing & Capabilities → Associated Domains → webcredentials:example.com
```

---

## Related

- `mobile-webauthn-workers-credential-storage.md`
- `biometric-auth.md`
- `react-native-biometric-auth.md`
- `capacitor-d1-sqlite-offline-sync.md`
- `android-nfc-workers-contactless-auth.md`

---

## Sources

- SimpleWebAuthn: https://simplewebauthn.dev/
- WebAuthn spec: https://www.w3.org/TR/webauthn-3/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Capacitor Biometrics: https://capacitorjs.com/docs/apis/
- Apple Associated Domains: https://developer.apple.com/documentation/xcode/supporting-associated-domains
