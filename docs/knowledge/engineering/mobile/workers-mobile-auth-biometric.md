# Biometric Authentication Flow via Cloudflare Workers (WebAuthn / Passkeys)

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Mobile apps that rely solely on username/password authentication face phishing risk and poor UX. Biometric login (Face ID, Touch ID, fingerprint) tied to a device-bound passkey eliminates shared-secret risk. You need a backend that issues WebAuthn challenges, verifies assertions, and stores credentials — all without running a full authentication server.

## Context

A Cloudflare Worker implements the server side of the WebAuthn authentication ceremony. Challenges are issued and stored in KV with a 5-minute TTL. Credential public keys are persisted in D1. Assertion verification uses the Workers `SubtleCrypto` API (no external libraries). A separate flow handles fallback to PIN/password and cross-device credential sync hints.

## Solution

```typescript
// biometric-auth/src/index.ts
import { Hono } from 'hono';
import { Buffer } from 'node:buffer';

export interface Env {
  CHALLENGES: KVNamespace;   // key: challengeId => base64url challenge, TTL 300s
  CREDENTIALS: D1Database;   // table: webauthn_credentials
  JWT_SECRET: string;        // Worker secret
}

// ── helpers ──────────────────────────────────────────────────────────────────

function b64urlToBuffer(b64: string): ArrayBuffer {
  const base64 = b64.replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(base64);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0)).buffer;
}

function bufferToB64url(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

function randomBytes(length: number): Uint8Array {
  const buf = new Uint8Array(length);
  crypto.getRandomValues(buf);
  return buf;
}

// Parse the authenticatorData from a WebAuthn assertion
function parseAuthenticatorData(buf: ArrayBuffer): {
  rpIdHash: ArrayBuffer;
  flags: number;
  signCount: number;
} {
  const view = new DataView(buf);
  return {
    rpIdHash: buf.slice(0, 32),
    flags: view.getUint8(32),
    signCount: view.getUint32(33, false), // big-endian
  };
}

async function verifyAssertion(
  credentialPublicKeyJwk: JsonWebKey,
  clientDataJSON: ArrayBuffer,
  authenticatorData: ArrayBuffer,
  signature: ArrayBuffer,
): Promise<boolean> {
  // Import stored public key (ES256 / P-256)
  const publicKey = await crypto.subtle.importKey(
    'jwk',
    credentialPublicKeyJwk,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['verify'],
  );

  // Verification data = authData || SHA-256(clientDataJSON)
  const clientDataHash = await crypto.subtle.digest('SHA-256', clientDataJSON);
  const verificationData = new Uint8Array(
    authenticatorData.byteLength + clientDataHash.byteLength,
  );
  verificationData.set(new Uint8Array(authenticatorData), 0);
  verificationData.set(new Uint8Array(clientDataHash), authenticatorData.byteLength);

  return crypto.subtle.verify(
    { name: 'ECDSA', hash: 'SHA-256' },
    publicKey,
    signature,
    verificationData,
  );
}

async function signJwt(payload: Record<string, unknown>, secret: string): Promise<string> {
  const header = { alg: 'HS256', typ: 'JWT' };
  const encode = (obj: unknown) =>
    bufferToB64url(new TextEncoder().encode(JSON.stringify(obj)).buffer);
  const headerB64 = encode(header);
  const payloadB64 = encode(payload);
  const signingInput = `${headerB64}.${payloadB64}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(signingInput));
  return `${signingInput}.${bufferToB64url(sig)}`;
}

// ── routes ────────────────────────────────────────────────────────────────────

const app = new Hono<{ Bindings: Env }>();

// Step 1 — issue a challenge
app.post('/auth/biometric/challenge', async (c) => {
  const { user_id } = await c.req.json<{ user_id: string }>();
  if (!user_id) return c.json({ error: 'user_id required' }, 400);

  const challengeId = bufferToB64url(randomBytes(16).buffer);
  const challenge = bufferToB64url(randomBytes(32).buffer);

  // Bind challenge to user_id to prevent cross-user replay
  await c.env.CHALLENGES.put(
    challengeId,
    JSON.stringify({ challenge, user_id }),
    { expirationTtl: 300 },
  );

  return c.json({ challenge_id: challengeId, challenge });
});

// Step 2 — verify assertion and issue JWT
app.post('/auth/biometric/verify', async (c) => {
  const body = await c.req.json<{
    challenge_id: string;
    credential_id: string;       // base64url
    client_data_json: string;    // base64url
    authenticator_data: string;  // base64url
    signature: string;           // base64url
    device_fingerprint: string;
  }>();

  // 1. Retrieve and consume challenge (one-time use)
  const raw = await c.env.CHALLENGES.get(body.challenge_id);
  if (!raw) return c.json({ error: 'Challenge expired or not found' }, 401);
  await c.env.CHALLENGES.delete(body.challenge_id);

  const { challenge: expectedChallenge, user_id } = JSON.parse(raw) as {
    challenge: string;
    user_id: string;
  };

  // 2. Decode clientDataJSON and confirm challenge + origin
  const clientDataJSON = b64urlToBuffer(body.client_data_json);
  const clientData = JSON.parse(new TextDecoder().decode(clientDataJSON)) as {
    type: string;
    challenge: string;
    origin: string;
  };

  if (clientData.type !== 'webauthn.get')
    return c.json({ error: 'Invalid clientData type' }, 401);
  if (clientData.challenge !== expectedChallenge)
    return c.json({ error: 'Challenge mismatch' }, 401);

  // 3. Load stored credential
  const cred = await c.env.CREDENTIALS.prepare(
    'SELECT public_key_jwk, sign_count, device_fingerprint FROM webauthn_credentials WHERE credential_id = ? AND user_id = ?',
  )
    .bind(body.credential_id, user_id)
    .first<{ public_key_jwk: string; sign_count: number; device_fingerprint: string }>();

  if (!cred) return c.json({ error: 'Credential not found' }, 401);

  // 4. Verify signature
  const authData = b64urlToBuffer(body.authenticator_data);
  const { signCount } = parseAuthenticatorData(authData);

  const valid = await verifyAssertion(
    JSON.parse(cred.public_key_jwk) as JsonWebKey,
    clientDataJSON,
    authData,
    b64urlToBuffer(body.signature),
  );
  if (!valid) return c.json({ error: 'Signature verification failed' }, 401);

  // 5. Replay-attack guard: sign count must increase
  if (signCount !== 0 && signCount <= cred.sign_count) {
    return c.json({ error: 'Authenticator cloned or replayed' }, 401);
  }

  // 6. Persist new sign count
  await c.env.CREDENTIALS.prepare(
    'UPDATE webauthn_credentials SET sign_count = ?, last_used_at = ? WHERE credential_id = ?',
  )
    .bind(signCount, new Date().toISOString(), body.credential_id)
    .run();

  // 7. Issue JWT
  const token = await signJwt(
    { sub: user_id, iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 900 },
    c.env.JWT_SECRET,
  );

  return c.json({ access_token: token, token_type: 'Bearer', expires_in: 900 });
});

// PIN/password fallback — issues same JWT structure so clients are agnostic
app.post('/auth/password', async (c) => {
  const { user_id, password } = await c.req.json<{ user_id: string; password: string }>();
  // ... validate password against D1 (bcrypt comparison via WASM) ...
  const token = await signJwt(
    { sub: user_id, iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 900, auth_method: 'password' },
    c.env.JWT_SECRET,
  );
  return c.json({ access_token: token, token_type: 'Bearer', expires_in: 900 });
});

export default app;
```

## Implementation Details

**D1 schema:**
```sql
CREATE TABLE webauthn_credentials (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          TEXT NOT NULL,
  credential_id    TEXT NOT NULL UNIQUE,
  public_key_jwk   TEXT NOT NULL,  -- JSON-serialised JWK
  sign_count       INTEGER NOT NULL DEFAULT 0,
  device_name      TEXT,
  device_fingerprint TEXT,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  last_used_at     TEXT
);
CREATE INDEX idx_cred_user ON webauthn_credentials(user_id);
```

**Registration** (not shown above) calls `navigator.credentials.create()` on the client, receives the new credential's public key in COSE format, converts it to JWK, and stores it via a `POST /auth/biometric/register` endpoint that follows the same D1 insert pattern.

**Cross-device sync** — iCloud Keychain and Google Password Manager sync passkeys automatically. The Worker does not need to implement sync itself; store multiple `webauthn_credentials` rows per `user_id` and allow each device's credential to authenticate independently.

**Fallback** — if biometric prompt fails (too many attempts, hardware fault) the client hits `POST /auth/password`. The response shape is identical so the token refresh path requires no branching.

## Anti-patterns

- **Storing the challenge in a cookie or response body** beyond the initial issuance. The challenge must be consumed server-side (deleted from KV) on first use to prevent replay.
- **Skipping the sign-count check.** An always-zero count from a soft authenticator is acceptable (set to 0), but a decreasing count from a previously-non-zero authenticator signals a cloned key.
- **Verifying the RP ID hash client-side.** The Worker must verify `rpIdHash` in `authenticatorData` equals `SHA-256` of your registered origin domain.
- **Long-lived JWTs from biometric login.** Issue the same short-lived (15 min) access tokens and pair with refresh token rotation.

## Gotchas

- `SubtleCrypto.verify` with ECDSA expects the signature in DER format (ASN.1), not the raw IEEE P1363 format some authenticators produce. Add a DER-to-raw conversion if you see unexpected verification failures on Android.
- KV `expirationTtl` has a minimum of 60 seconds. A 5-minute challenge TTL (`300`) is safe and gives users adequate time to respond to the biometric prompt.
- Workers `crypto.subtle` is synchronous for key import but async for sign/verify. All calls must be awaited.
- `JSON.parse` on the stored JWK must round-trip cleanly; avoid any serialisation that drops `undefined` fields from the JWK object.

## Verification

```bash
# 1. Request a challenge
CHALLENGE=$(curl -s -X POST https://api.example.com/auth/biometric/challenge \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"user_abc"}' | jq -r '.challenge')
echo "Challenge: $CHALLENGE"

# 2. (On device) sign the challenge with the passkey, then
# POST /auth/biometric/verify with the assertion fields

# 3. Confirm JWT is returned
curl -s -X POST https://api.example.com/auth/biometric/verify \
  -H 'Content-Type: application/json' \
  -d '{"challenge_id":"...","credential_id":"...", ...}' | jq .access_token
```

## Related

- `documentation/docs/policies/mobile/workers-session-refresh-token-rotation.md` — access/refresh token lifecycle
- `documentation/docs/policies/mobile/push-notification-fcm-apns.md` — device registration alongside credential registration
- `documentation/docs/policies/mobile/device-detection.md` — platform detection for biometric capability checks

## Sources

- WebAuthn Level 3 specification: https://www.w3.org/TR/webauthn-3/
- Cloudflare Workers SubtleCrypto: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- Cloudflare KV: https://developers.cloudflare.com/kv/
- Cloudflare D1: https://developers.cloudflare.com/d1/
