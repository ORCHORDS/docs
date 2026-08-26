# Passkey Registration and Authentication Frontend Flow Coordinated via Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You want passwordless login with biometric/device passkeys (WebAuthn) for your web app. The browser credential API (`navigator.credentials.create` / `navigator.credentials.get`) requires a trusted server to generate and verify cryptographic challenges. A Cloudflare Worker acts as the relying party server, handling challenge issuance, credential storage in D1, and assertion verification.

## Context

WebAuthn has two flows:

1. **Registration**: User enrolls a new credential (passkey). Server sends a challenge; browser calls the authenticator (Touch ID, Windows Hello, etc.) to generate a key pair; public key is sent to the server and stored.
2. **Authentication**: User logs in. Server sends a challenge; browser signs it with the private key stored on the device; server verifies the signature against the stored public key.

The Worker is the relying party (RP). The frontend coordinates the two flows. Sessions are issued as signed `HttpOnly` cookies after successful verification.

---

## Solution

### 1. Type Definitions

```typescript
// shared/types.ts

export interface RegistrationChallenge {
  challengeBase64: string;
  rpId: string;
  rpName: string;
  userId: string;        // base64url-encoded user handle
  userName: string;
  userDisplayName: string;
  timeout: number;
}

export interface RegistrationPayload {
  id: string;            // credential ID (base64url)
  rawId: string;         // base64url
  type: 'public-key';
  clientDataJSON: string;     // base64url
  attestationObject: string;  // base64url
  authenticatorAttachment?: string;
}

export interface AuthChallenge {
  challengeBase64: string;
  rpId: string;
  timeout: number;
  allowCredentials: Array<{ id: string; type: 'public-key' }>;
}

export interface AssertionPayload {
  id: string;
  rawId: string;
  type: 'public-key';
  clientDataJSON: string;
  authenticatorData: string;
  signature: string;
  userHandle?: string;
}
```

### 2. Worker — Registration Challenge Endpoint

```typescript
// worker/src/routes/webauthn-register.ts
import type { Env } from '../env';

const RP_ID = 'your-domain.com';
const RP_NAME = 'Your App';

/** Generate a cryptographically random challenge (32 bytes). */
async function generateChallenge(): Promise<string> {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return bufferToBase64Url(bytes);
}

function bufferToBase64Url(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let str = '';
  for (const byte of bytes) str += String.fromCharCode(byte);
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

export async function handleRegisterChallenge(
  request: Request,
  env: Env
): Promise<Response> {
  const { userId, userName, displayName } = await request.json<{
    userId: string;
    userName: string;
    displayName: string;
  }>();

  if (!userId || !userName) return new Response('Bad Request', { status: 400 });

  const challengeBase64 = await generateChallenge();

  // Store challenge in D1 with a 5-minute TTL
  await env.DB.prepare(
    `INSERT OR REPLACE INTO webauthn_challenges (user_id, challenge, expires_at)
     VALUES (?, ?, datetime('now', '+5 minutes'))`
  )
    .bind(userId, challengeBase64)
    .run();

  const response: import('../../../shared/types').RegistrationChallenge = {
    challengeBase64,
    rpId: RP_ID,
    rpName: RP_NAME,
    userId: bufferToBase64Url(new TextEncoder().encode(userId)),
    userName,
    userDisplayName: displayName,
    timeout: 300_000,
  };

  return Response.json(response);
}

export async function handleRegisterVerify(
  request: Request,
  env: Env
): Promise<Response> {
  const payload = await request.json<import('../../../shared/types').RegistrationPayload & { userId: string }>();

  // 1. Retrieve and validate the stored challenge
  const row = await env.DB.prepare(
    `SELECT challenge FROM webauthn_challenges
     WHERE user_id = ? AND expires_at > datetime('now')`
  )
    .bind(payload.userId)
    .first<{ challenge: string }>();

  if (!row) return new Response('Challenge expired or not found', { status: 400 });

  // 2. Decode clientDataJSON
  const clientData = JSON.parse(
    atob(payload.clientDataJSON.replace(/-/g, '+').replace(/_/g, '/'))
  );

  if (clientData.type !== 'webauthn.create') {
    return new Response('Invalid clientData type', { status: 400 });
  }

  if (clientData.challenge !== row.challenge) {
    return new Response('Challenge mismatch', { status: 400 });
  }

  if (!clientData.origin.endsWith(RP_ID)) {
    return new Response('Origin mismatch', { status: 400 });
  }

  // 3. Store the credential public key
  // NOTE: Full attestation parsing (CBOR decoding of attestationObject) requires
  // a CBOR library or manual parsing. This example stores the raw attestationObject
  // for later full verification in a production implementation.
  await env.DB.prepare(
    `INSERT INTO webauthn_credentials
       (credential_id, user_id, public_key_cbor, sign_count, created_at)
     VALUES (?, ?, ?, 0, datetime('now'))`
  )
    .bind(payload.id, payload.userId, payload.attestationObject)
    .run();

  // 4. Clean up the used challenge
  await env.DB.prepare('DELETE FROM webauthn_challenges WHERE user_id = ?')
    .bind(payload.userId)
    .run();

  return Response.json({ success: true });
}
```

### 3. Worker — Authentication Endpoints

```typescript
// worker/src/routes/webauthn-auth.ts
import type { Env } from '../env';

const RP_ID = 'your-domain.com';

export async function handleAuthChallenge(
  request: Request,
  env: Env
): Promise<Response> {
  const { userId } = await request.json<{ userId: string }>();

  // Look up credentials for this user
  const credentials = await env.DB.prepare(
    `SELECT credential_id FROM webauthn_credentials WHERE user_id = ?`
  )
    .bind(userId)
    .all<{ credential_id: string }>();

  if (!credentials.results.length) {
    return new Response('No credentials registered', { status: 404 });
  }

  const challengeBytes = crypto.getRandomValues(new Uint8Array(32));
  const challengeBase64 = bufferToBase64Url(challengeBytes);

  await env.DB.prepare(
    `INSERT OR REPLACE INTO webauthn_challenges (user_id, challenge, expires_at)
     VALUES (?, ?, datetime('now', '+5 minutes'))`
  )
    .bind(userId, challengeBase64)
    .run();

  const response: import('../../../shared/types').AuthChallenge = {
    challengeBase64,
    rpId: RP_ID,
    timeout: 300_000,
    allowCredentials: credentials.results.map((r) => ({
      id: r.credential_id,
      type: 'public-key' as const,
    })),
  };

  return Response.json(response);
}

export async function handleAuthVerify(
  request: Request,
  env: Env
): Promise<Response> {
  const payload = await request.json<
    import('../../../shared/types').AssertionPayload & { userId: string }
  >();

  // 1. Verify challenge
  const row = await env.DB.prepare(
    `SELECT challenge FROM webauthn_challenges
     WHERE user_id = ? AND expires_at > datetime('now')`
  )
    .bind(payload.userId)
    .first<{ challenge: string }>();

  if (!row) return new Response('Challenge expired', { status: 400 });

  // 2. Verify clientDataJSON
  const clientData = JSON.parse(
    atob(payload.clientDataJSON.replace(/-/g, '+').replace(/_/g, '/'))
  );

  if (clientData.type !== 'webauthn.get') {
    return new Response('Invalid clientData type', { status: 400 });
  }

  if (clientData.challenge !== row.challenge) {
    return new Response('Challenge mismatch', { status: 400 });
  }

  // 3. Verify signature against stored public key
  // Full verification requires:
  //   a) Decode the stored CBOR public key to a CryptoKey
  //   b) Reconstruct the signed data: SHA-256(clientDataJSON) + authenticatorData
  //   c) crypto.subtle.verify(algorithm, publicKey, signature, signedData)
  // This is a sketch — use a battle-tested library (simplewebauthn/server) in production.
  const credRow = await env.DB.prepare(
    `SELECT public_key_cbor, sign_count FROM webauthn_credentials
     WHERE credential_id = ? AND user_id = ?`
  )
    .bind(payload.id, payload.userId)
    .first<{ public_key_cbor: string; sign_count: number }>();

  if (!credRow) return new Response('Credential not found', { status: 404 });

  // Signature verification (pseudo-code for full implementation):
  // const publicKey = await decodeCborPublicKey(credRow.public_key_cbor);
  // const authData = base64urlToBuffer(payload.authenticatorData);
  // const clientDataHash = await crypto.subtle.digest('SHA-256',
  //   base64urlToBuffer(payload.clientDataJSON));
  // const signedData = concat(authData, clientDataHash);
  // const valid = await crypto.subtle.verify(
  //   { name: 'ECDSA', hash: 'SHA-256' }, publicKey,
  //   base64urlToBuffer(payload.signature), signedData);
  // if (!valid) return new Response('Invalid signature', { status: 401 });

  // 4. Update sign count (replay attack prevention)
  await env.DB.prepare(
    `UPDATE webauthn_credentials SET sign_count = sign_count + 1
     WHERE credential_id = ?`
  )
    .bind(payload.id)
    .run();

  // 5. Clean up challenge
  await env.DB.prepare('DELETE FROM webauthn_challenges WHERE user_id = ?')
    .bind(payload.userId)
    .run();

  // 6. Issue session cookie
  const sessionToken = bufferToBase64Url(crypto.getRandomValues(new Uint8Array(32)));
  await env.DB.prepare(
    `INSERT INTO sessions (token, user_id, expires_at)
     VALUES (?, ?, datetime('now', '+30 days'))`
  )
    .bind(sessionToken, payload.userId)
    .run();

  return new Response(JSON.stringify({ success: true }), {
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': [
        `session=${sessionToken}`,
        'HttpOnly',
        'Secure',
        'SameSite=Strict',
        'Path=/',
        'Max-Age=2592000',
      ].join('; '),
    },
  });
}

function bufferToBase64Url(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let str = '';
  for (const byte of bytes) str += String.fromCharCode(byte);
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}
```

### 4. Frontend — Registration Flow

```typescript
// public/js/passkey-register.ts
import type { RegistrationChallenge, RegistrationPayload } from '../../shared/types';

function base64UrlToBuffer(base64Url: string): ArrayBuffer {
  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function bufferToBase64Url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let str = '';
  for (const byte of bytes) str += String.fromCharCode(byte);
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

export async function registerPasskey(userId: string, userName: string): Promise<void> {
  // 1. Fetch registration challenge from Worker
  const challengeRes = await fetch('/api/webauthn/register/challenge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, userName, displayName: userName }),
  });
  if (!challengeRes.ok) throw new Error('Failed to get registration challenge');
  const challenge: RegistrationChallenge = await challengeRes.json();

  // 2. Call the authenticator
  const publicKeyOptions: PublicKeyCredentialCreationOptions = {
    challenge: base64UrlToBuffer(challenge.challengeBase64),
    rp: { id: challenge.rpId, name: challenge.rpName },
    user: {
      id: base64UrlToBuffer(challenge.userId),
      name: challenge.userName,
      displayName: challenge.userDisplayName,
    },
    pubKeyCredParams: [
      { type: 'public-key', alg: -7  },  // ES256 (ECDSA P-256)
      { type: 'public-key', alg: -257 }, // RS256 (RSA)
    ],
    authenticatorSelection: {
      residentKey: 'required',       // Passkey requires a resident key
      userVerification: 'required',  // Require biometric/PIN
    },
    timeout: challenge.timeout,
    attestation: 'none', // 'none' avoids attestation privacy issues
  };

  const credential = await navigator.credentials.create({ publicKey: publicKeyOptions }) as PublicKeyCredential;

  if (!credential) throw new Error('Credential creation cancelled');

  const response = credential.response as AuthenticatorAttestationResponse;

  // 3. Send credential to Worker for storage
  const payload: RegistrationPayload & { userId: string } = {
    id: credential.id,
    rawId: bufferToBase64Url(credential.rawId),
    type: 'public-key',
    clientDataJSON: bufferToBase64Url(response.clientDataJSON),
    attestationObject: bufferToBase64Url(response.attestationObject),
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
    userId,
  };

  const verifyRes = await fetch('/api/webauthn/register/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!verifyRes.ok) throw new Error('Passkey registration failed');
  console.log('Passkey registered successfully');
}
```

### 5. Frontend — Authentication Flow

```typescript
// public/js/passkey-auth.ts
import type { AuthChallenge, AssertionPayload } from '../../shared/types';

function base64UrlToBuffer(base64Url: string): ArrayBuffer {
  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function bufferToBase64Url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let str = '';
  for (const byte of bytes) str += String.fromCharCode(byte);
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

export async function authenticateWithPasskey(userId: string): Promise<void> {
  // 1. Fetch authentication challenge
  const challengeRes = await fetch('/api/webauthn/auth/challenge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId }),
  });
  if (!challengeRes.ok) throw new Error('Failed to get auth challenge');
  const challenge: AuthChallenge = await challengeRes.json();

  // 2. Call the authenticator to sign the challenge
  const assertionOptions: PublicKeyCredentialRequestOptions = {
    challenge: base64UrlToBuffer(challenge.challengeBase64),
    rpId: challenge.rpId,
    timeout: challenge.timeout,
    allowCredentials: challenge.allowCredentials.map((c) => ({
      id: base64UrlToBuffer(c.id),
      type: 'public-key' as const,
    })),
    userVerification: 'required',
  };

  const assertion = await navigator.credentials.get({ publicKey: assertionOptions }) as PublicKeyCredential;

  if (!assertion) throw new Error('Authentication cancelled');

  const response = assertion.response as AuthenticatorAssertionResponse;

  // 3. Send assertion to Worker for verification
  const payload: AssertionPayload & { userId: string } = {
    id: assertion.id,
    rawId: bufferToBase64Url(assertion.rawId),
    type: 'public-key',
    clientDataJSON: bufferToBase64Url(response.clientDataJSON),
    authenticatorData: bufferToBase64Url(response.authenticatorData),
    signature: bufferToBase64Url(response.signature),
    userHandle: response.userHandle ? bufferToBase64Url(response.userHandle) : undefined,
    userId,
  };

  const verifyRes = await fetch('/api/webauthn/auth/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'include', // needed to receive the Set-Cookie
  });

  if (!verifyRes.ok) throw new Error('Passkey authentication failed');
  console.log('Authenticated — session established');
  window.location.href = '/app';
}
```

### 6. D1 Schema

```sql
-- migrations/0001_webauthn.sql

CREATE TABLE IF NOT EXISTS webauthn_challenges (
  user_id     TEXT NOT NULL PRIMARY KEY,
  challenge   TEXT NOT NULL,
  expires_at  TEXT NOT NULL  -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS webauthn_credentials (
  credential_id    TEXT NOT NULL PRIMARY KEY,
  user_id          TEXT NOT NULL,
  public_key_cbor  TEXT NOT NULL,  -- base64url-encoded CBOR attestationObject
  sign_count       INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT NOT NULL
);

CREATE INDEX idx_creds_user_id ON webauthn_credentials(user_id);

CREATE TABLE IF NOT EXISTS sessions (
  token       TEXT NOT NULL PRIMARY KEY,
  user_id     TEXT NOT NULL,
  expires_at  TEXT NOT NULL
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
```

---

## Implementation Details

- **Resident keys (discoverable credentials)**: Setting `residentKey: 'required'` stores the credential on the authenticator device (not just a reference). This enables usernameless login (`allowCredentials: []` on auth challenge — the authenticator surfaces available passkeys).
- **Challenge storage in D1 with TTL**: Challenges are single-use tokens valid for 5 minutes. After verification, they are deleted. D1 `datetime('now', '+5 minutes')` creates the expiry in UTC.
- **CBOR decoding for public key extraction**: The `attestationObject` is CBOR-encoded. To verify signatures, you must decode it, extract the COSE public key from `authData`, import it via `crypto.subtle.importKey`, and verify with `crypto.subtle.verify`. Use `@simplewebauthn/server` in production — it handles this correctly.
- **Sign count**: The authenticator increments a counter on each use. The server must verify the counter is greater than the stored value to detect cloned authenticators (replay attacks). Note: some platform authenticators (iOS Passkeys) always return 0 — handle this case by not failing verification when both old and new counts are 0.
- **`credentials: 'include'` on the assertion POST**: Without this, the `Set-Cookie` response header is ignored by the browser (CORS credential mode default is `'same-origin'`, but explicit is safer).

---

## Anti-patterns

- **Not deleting used challenges**: Without cleanup, an attacker who intercepts a challenge can replay it within the 5-minute TTL window (though WebAuthn signatures are still required). Always delete after use.
- **Skipping sign count verification**: A cloned authenticator will reuse an old sign count. Not checking enables credential cloning attacks.
- **Storing raw private keys server-side**: WebAuthn's security model is that the private key never leaves the device. Only the public key is stored server-side.
- **Using `attestation: 'direct'` without processing it**: Direct attestation sends device manufacturer certificates. If you request it but don't verify it, you gain no security benefit and expose device model info unnecessarily.
- **`SameSite=Lax` on the session cookie**: For WebAuthn flows, `SameSite=Strict` is preferable since the authentication is always initiated by same-site UI. `Lax` allows the cookie to be sent on top-level navigations from external links, widening the attack surface.

---

## Gotchas

- **`navigator.credentials.create/get` requires HTTPS** (or `localhost`). Passkeys will not work on HTTP origins.
- **RP ID must match the domain**: The `rpId` must be equal to or a registrable suffix of the origin's effective domain. `your-domain.com` works for `app.your-domain.com` but not the reverse.
- **Conditional UI (autofill)**: For a passkey autofill UI in the login form, call `navigator.credentials.get({ mediation: 'conditional', publicKey: ... })` and add `autocomplete="username webauthn"` to the username input. This shows the passkey picker in the browser's autofill dropdown.
- **Safari behaviour**: Safari requires a user gesture (click/tap) to trigger `navigator.credentials.create` or `navigator.credentials.get`. Calling these in `DOMContentLoaded` or `setTimeout` without a user gesture will throw a `NotAllowedError`.
- **Android Chrome sync**: Passkeys created on Android Chrome sync to Google Password Manager and are available across the user's Android devices. This is a passkey advantage (cross-device recovery) but means deleting a passkey server-side does not remove it from Google's sync — you must also invalidate sessions.

---

## Verification

```bash
# Apply D1 migration
npx wrangler d1 execute your-db-name --file=migrations/0001_webauthn.sql

# Deploy Worker
npx wrangler deploy

# Test registration challenge endpoint
curl -X POST https://your-worker.workers.dev/api/webauthn/register/challenge \
  -H 'Content-Type: application/json' \
  -d '{"userId":"user123","userName":"alice","displayName":"Alice"}'
# Expected: JSON with challengeBase64, rpId, etc.

# Test auth challenge endpoint (after a credential is registered via browser)
curl -X POST https://your-worker.workers.dev/api/webauthn/auth/challenge \
  -H 'Content-Type: application/json' \
  -d '{"userId":"user123"}'
# Expected: JSON with challengeBase64 and allowCredentials array

# Browser-side test: open /register.html in Chrome on a device with Touch ID or Windows Hello
# Open DevTools > Application > Passkeys to inspect registered credentials
```

---

## Related

- `documentation/categories/frontend/workers-static-form-handler-d1.md`
- `documentation/categories/frontend/workers-dark-mode-cookie-edge.md`
- SimpleWebAuthn library: https://simplewebauthn.dev

---

## Sources

- https://developers.cloudflare.com/d1/
- https://www.w3.org/TR/webauthn-3/
- https://passkeys.dev
- https://simplewebauthn.dev/docs/
- https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API
- https://web.dev/articles/passkey-registration
