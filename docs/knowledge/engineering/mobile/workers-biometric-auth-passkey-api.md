# Passkey (WebAuthn) Authentication Backend in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You want to offer passwordless, biometric-backed sign-in (Face ID, Touch ID, Windows Hello, Android fingerprint) in your mobile PWA or native web app. You need a lightweight backend that handles WebAuthn registration and authentication flows without a traditional server, storing credentials in D1 and performing cryptographic verification with the Web Crypto API built into the Workers runtime.

## Context

Passkeys are discoverable FIDO2/WebAuthn credentials tied to a platform authenticator (device biometrics) or a roaming authenticator (hardware key). The relying party (RP) backend must:

1. Generate and store a random `challenge` for each registration/authentication ceremony.
2. Verify the `clientDataJSON`, `authenticatorData`, and `signature` returned by the browser/OS.
3. Store the `credentialId` (base64url), `publicKey` (COSE-encoded), and `signCount` per user.
4. Reject replayed `signCount` values to prevent cloned-authenticator attacks.

Cloudflare Workers have access to `crypto.subtle` (Web Crypto API) natively, making Ed25519 and P-256 verification possible without external libraries.

## Solution

```typescript
// passkey-worker.ts
import { Hono } from 'hono';
import { cors } from 'hono/cors';

export interface Env {
  DB: D1Database;
  KV: KVNamespace;     // challenge storage (TTL 5 min)
  RP_ID: string;       // e.g. "example.com"
  RP_ORIGIN: string;   // e.g. "https://example.com"
  RP_NAME: string;     // e.g. "Example App"
}

const app = new Hono<{ Bindings: Env }>();
app.use('*', cors({ origin: (origin) => origin }));

// ── Helpers ───────────────────────────────────────────────────────────────────
function b64urlEncode(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

function b64urlDecode(s: string): ArrayBuffer {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(b64.padEnd(b64.length + (4 - (b64.length % 4)) % 4, '='));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0)).buffer;
}

function randomBytes(n: number): string {
  return b64urlEncode(crypto.getRandomValues(new Uint8Array(n)).buffer);
}

// ── Registration: generate challenge ─────────────────────────────────────────
app.post('/passkey/register/begin', async (c) => {
  const { userId, userName, userDisplayName } = await c.req.json<{
    userId: string;
    userName: string;
    userDisplayName: string;
  }>();

  const challenge = randomBytes(32);

  // Store challenge with 5-minute TTL keyed to userId
  await c.env.KV.put(`reg_challenge:${userId}`, challenge, { expirationTtl: 300 });

  // Fetch existing credentials to exclude (prevents re-registration of same authenticator)
  const { results } = await c.env.DB.prepare(
    'SELECT credential_id FROM passkeys WHERE user_id = ?'
  ).bind(userId).all<{ credential_id: string }>();

  const excludeCredentials = results.map((r) => ({
    id: r.credential_id,
    type: 'public-key',
    transports: ['internal', 'hybrid'],
  }));

  const options = {
    challenge,
    rp: { id: c.env.RP_ID, name: c.env.RP_NAME },
    user: {
      id: b64urlEncode(new TextEncoder().encode(userId).buffer),
      name: userName,
      displayName: userDisplayName,
    },
    pubKeyCredParams: [
      { type: 'public-key', alg: -7  },  // ES256 (P-256)
      { type: 'public-key', alg: -257 }, // RS256
    ],
    authenticatorSelection: {
      residentKey: 'required',
      userVerification: 'required',
    },
    timeout: 60000,
    excludeCredentials,
  };

  return c.json(options);
});

// ── Registration: verify and store credential ─────────────────────────────────
app.post('/passkey/register/complete', async (c) => {
  const { userId, credential } = await c.req.json<{ userId: string; credential: any }>();

  const storedChallenge = await c.env.KV.get(`reg_challenge:${userId}`);
  if (!storedChallenge) return c.json({ error: 'Challenge expired or not found' }, 400);

  // Decode clientDataJSON
  const clientData = JSON.parse(
    new TextDecoder().decode(b64urlDecode(credential.response.clientDataJSON))
  );

  if (clientData.type !== 'webauthn.create') return c.json({ error: 'Wrong type' }, 400);
  if (clientData.challenge !== storedChallenge) return c.json({ error: 'Challenge mismatch' }, 400);
  if (clientData.origin !== c.env.RP_ORIGIN) return c.json({ error: 'Origin mismatch' }, 400);

  // Parse authenticatorData (first 37 bytes are fixed structure)
  const authData = new Uint8Array(b64urlDecode(credential.response.authenticatorData));
  const rpIdHash = authData.slice(0, 32);
  const flags = authData[32];
  const userPresent = (flags & 0x01) !== 0;
  const userVerified = (flags & 0x04) !== 0;

  if (!userPresent || !userVerified) {
    return c.json({ error: 'User presence/verification required' }, 400);
  }

  // Verify RP ID hash
  const expectedRpIdHash = new Uint8Array(
    await crypto.subtle.digest('SHA-256', new TextEncoder().encode(c.env.RP_ID))
  );
  const rpIdMatch = expectedRpIdHash.every((b, i) => b === rpIdHash[i]);
  if (!rpIdMatch) return c.json({ error: 'RP ID mismatch' }, 400);

  const signCount =
    new DataView(authData.buffer).getUint32(33, false); // big-endian at offset 33

  // Store credential in D1
  await c.env.DB.prepare(
    `INSERT OR REPLACE INTO passkeys
       (user_id, credential_id, public_key_cose, sign_count, created_at, last_used_at)
     VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))`
  )
    .bind(
      userId,
      credential.id,
      credential.response.publicKey ?? '',
      signCount
    )
    .run();

  // Invalidate challenge
  await c.env.KV.delete(`reg_challenge:${userId}`);

  return c.json({ verified: true });
});

// ── Authentication: generate challenge ────────────────────────────────────────
app.post('/passkey/auth/begin', async (c) => {
  const { userId } = await c.req.json<{ userId?: string }>();

  const challenge = randomBytes(32);
  const sessionId = randomBytes(16);

  await c.env.KV.put(
    `auth_challenge:${sessionId}`,
    JSON.stringify({ challenge, userId: userId ?? null }),
    { expirationTtl: 300 }
  );

  let allowCredentials: any[] = [];
  if (userId) {
    const { results } = await c.env.DB.prepare(
      'SELECT credential_id FROM passkeys WHERE user_id = ?'
    ).bind(userId).all<{ credential_id: string }>();
    allowCredentials = results.map((r) => ({
      id: r.credential_id,
      type: 'public-key',
      transports: ['internal', 'hybrid'],
    }));
  }

  return c.json({
    sessionId,
    options: {
      challenge,
      rpId: c.env.RP_ID,
      allowCredentials,
      userVerification: 'required',
      timeout: 60000,
    },
  });
});

// ── Authentication: verify signature ─────────────────────────────────────────
app.post('/passkey/auth/complete', async (c) => {
  const { sessionId, credential } = await c.req.json<{ sessionId: string; credential: any }>();

  const stored = await c.env.KV.get(`auth_challenge:${sessionId}`);
  if (!stored) return c.json({ error: 'Challenge expired' }, 400);
  const { challenge: storedChallenge, userId: storedUserId } = JSON.parse(stored);

  // Decode clientDataJSON
  const clientData = JSON.parse(
    new TextDecoder().decode(b64urlDecode(credential.response.clientDataJSON))
  );
  if (clientData.type !== 'webauthn.get') return c.json({ error: 'Wrong type' }, 400);
  if (clientData.challenge !== storedChallenge) return c.json({ error: 'Challenge mismatch' }, 400);
  if (clientData.origin !== c.env.RP_ORIGIN) return c.json({ error: 'Origin mismatch' }, 400);

  // Load stored credential
  const row = await c.env.DB.prepare(
    'SELECT user_id, public_key_cose, sign_count FROM passkeys WHERE credential_id = ?'
  ).bind(credential.id).first<{ user_id: string; public_key_cose: string; sign_count: number }>();

  if (!row) return c.json({ error: 'Credential not found' }, 400);
  if (storedUserId && row.user_id !== storedUserId) return c.json({ error: 'User mismatch' }, 400);

  // Parse authenticatorData for signCount
  const authData = new Uint8Array(b64urlDecode(credential.response.authenticatorData));
  const newSignCount = new DataView(authData.buffer).getUint32(33, false);

  if (newSignCount !== 0 && newSignCount <= row.sign_count) {
    return c.json({ error: 'Cloned authenticator detected: signCount did not increase' }, 400);
  }

  // Verify signature using Web Crypto (P-256 / ES256)
  // clientDataHash = SHA-256(clientDataJSON bytes)
  const clientDataBytes = b64urlDecode(credential.response.clientDataJSON);
  const clientDataHash = await crypto.subtle.digest('SHA-256', clientDataBytes);

  const signedData = new Uint8Array(authData.length + 32);
  signedData.set(authData);
  signedData.set(new Uint8Array(clientDataHash), authData.length);

  // Import the stored COSE public key as a SubjectPublicKeyInfo (DER) CryptoKey
  // Note: row.public_key_cose is stored as base64url of the DER-encoded key
  const pubKeyDer = b64urlDecode(row.public_key_cose);
  const cryptoKey = await crypto.subtle.importKey(
    'spki',
    pubKeyDer,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['verify']
  );

  const sig = b64urlDecode(credential.response.signature);
  const valid = await crypto.subtle.verify(
    { name: 'ECDSA', hash: 'SHA-256' },
    cryptoKey,
    sig,
    signedData
  );

  if (!valid) return c.json({ error: 'Signature verification failed' }, 401);

  // Update signCount and last_used_at
  await c.env.DB.prepare(
    `UPDATE passkeys SET sign_count = ?, last_used_at = datetime('now') WHERE credential_id = ?`
  ).bind(newSignCount, credential.id).run();

  await c.env.KV.delete(`auth_challenge:${sessionId}`);

  return c.json({ verified: true, userId: row.user_id });
});

// ── Passkey deletion ──────────────────────────────────────────────────────────
app.delete('/passkey/:credentialId', async (c) => {
  // Caller must provide a valid session token — simplified here
  const authHeader = c.req.header('Authorization') ?? '';
  const userId = await resolveUserFromSession(authHeader, c.env);
  if (!userId) return c.json({ error: 'Unauthorized' }, 401);

  const credentialId = c.req.param('credentialId');
  const { meta } = await c.env.DB.prepare(
    'DELETE FROM passkeys WHERE credential_id = ? AND user_id = ?'
  ).bind(credentialId, userId).run();

  if (meta.changes === 0) return c.json({ error: 'Not found or not yours' }, 404);
  return c.json({ deleted: true });
});

async function resolveUserFromSession(authHeader: string, env: Env): Promise<string | null> {
  const token = authHeader.replace('Bearer ', '').trim();
  if (!token) return null;
  return await env.KV.get(`session:${token}`);
}

export default app;
```

```sql
-- D1 migration: 001_passkeys.sql
CREATE TABLE IF NOT EXISTS passkeys (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id        TEXT    NOT NULL,
  credential_id  TEXT    NOT NULL UNIQUE,
  public_key_cose TEXT   NOT NULL,
  sign_count     INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT    NOT NULL,
  last_used_at   TEXT    NOT NULL
);
CREATE INDEX idx_passkeys_user_id       ON passkeys(user_id);
CREATE INDEX idx_passkeys_credential_id ON passkeys(credential_id);
```

## Implementation Details

- **Challenge TTL via KV**: Challenges are stored in KV with a 300-second TTL. KV's built-in expiry handles cleanup with no cron job required.
- **signCount monotonicity**: A `signCount` that does not increase (and is not zero) is a FIDO2 red flag for cloned authenticators. Store and compare it on every authentication.
- **Public key format**: The browser returns the public key as COSE-encoded bytes. During registration, the `credential.response.publicKey` field is a base64url-encoded SubjectPublicKeyInfo (SPKI) DER blob — use it directly with `importKey('spki', ...)`. If the browser does not populate `publicKey`, parse it from `attestationObject`.
- **Multi-device credentials**: A single `userId` can have multiple rows in `passkeys`. List them all and let the user manage them by `credential_id`.
- **No attestation verification**: This implementation skips attestation verification (checking that the authenticator is a genuine TPM/Secure Enclave). For consumer apps this is usually acceptable; for high-security flows parse and verify the `attestationObject`.

## Anti-patterns

- **Storing challenges in a cookie or response body**: Challenges must be server-side and single-use. Sending the challenge in a cookie and re-reading it makes CSRF possible.
- **Skipping origin check**: Accepting any origin lets an attacker use a credential registered on `evil.com` to authenticate on your domain.
- **Using localStorage for the credential**: The browser's `navigator.credentials` API manages passkeys internally. Never serialize or store private key material yourself.
- **Reusing the same challenge**: Generate a fresh random challenge per ceremony. Never cache or reuse challenges.

## Gotchas

- `crypto.subtle.importKey` with `'spki'` for P-256 keys requires the full DER-encoded SubjectPublicKeyInfo, not the raw 64-byte XY coordinates. The `response.publicKey` field from the browser is already in this format.
- The `signCount` field in `authenticatorData` is at byte offset 33 as a big-endian `uint32`. Use `DataView.getUint32(33, false)` — `false` = big-endian.
- Android's `PublicKeyCredential.response.publicKey` is available since Chrome 109. Older Android WebViews may not populate it; fall back to parsing `attestationObject`.
- KV replication is eventually consistent. In rare cases a challenge written in one edge location may not be visible in another for a few hundred milliseconds. For strict consistency, use D1 for challenge storage (at the cost of one extra DB round-trip).

## Verification

```bash
# 1. Register a passkey (simulated with test data)
curl -s -X POST https://example.com/passkey/register/begin \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u1","userName":"alice","userDisplayName":"Alice"}' | jq .

# 2. List registered passkeys for a user
npx wrangler d1 execute example project-main \
  --command "SELECT credential_id, sign_count, last_used_at FROM passkeys WHERE user_id='u1'"

# 3. Check KV challenge entries (should be empty after completion)
npx wrangler kv key list --binding KV --prefix reg_challenge:

# 4. Passkey library for testing without a real authenticator
# Use SimpleWebAuthn's server library in unit tests:
npm install @simplewebauthn/server
```

## Related

- `workers-mobile-api-rate-limiting-kv.md` — rate-limit registration/authentication endpoints
- `workers-app-version-gating-kv.md` — require minimum app version before allowing passkey registration
- `workers-deep-link-routing-universal-links.md` — deep link into passkey management screens

## Sources

- https://www.w3.org/TR/webauthn-3/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/d1/
- https://simplewebauthn.dev/docs/packages/server
- https://fidoalliance.org/passkeys/
