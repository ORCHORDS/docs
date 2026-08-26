# Passkey (WebAuthn) Registration and Authentication in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want password-free, phishing-resistant authentication for your Workers-based app. Users should be able to register a passkey (Touch ID, Face ID, hardware key) and log in without a password. The challenge nonce must be short-lived, the credential public key must be persisted, and all cryptographic verification must happen inside the Worker runtime using WebCrypto.

## Context

WebAuthn is a W3C standard that lets a browser (or OS) act as an authenticator. The server issues a random challenge, the authenticator signs it with a device-bound private key, and the server verifies the signature against the stored public key. Cloudflare Workers expose the Web Crypto API (`crypto.subtle`) natively, D1 is a natural fit for credential storage, and KV is ideal for ephemeral challenge storage because it supports per-key TTLs.

Runtime: Cloudflare Workers (TypeScript, `@cloudflare/workers-types`)
Storage: D1 (credentials), KV (challenge nonces)
Crypto: `crypto.subtle` (built-in, no npm dependency needed)

## D1 Schema

```sql
-- Run once via wrangler d1 execute
CREATE TABLE IF NOT EXISTS webauthn_credentials (
  id                TEXT PRIMARY KEY,          -- base64url credential ID
  user_id           TEXT NOT NULL,
  public_key_spki   TEXT NOT NULL,             -- base64url SPKI-encoded public key
  sign_count        INTEGER NOT NULL DEFAULT 0,
  aaguid            TEXT,
  created_at        INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_webauthn_user ON webauthn_credentials(user_id);
```

## KV Namespace (wrangler.toml)

```toml
[[kv_namespaces]]
binding = "CHALLENGES"
id      = "<your-kv-namespace-id>"

[[d1_databases]]
binding  = "DB"
database_name = "app-db"
database_id   = "<your-d1-id>"
```

## Registration: Issue Challenge

```typescript
// src/handlers/webauthn-register-challenge.ts
import type { Env } from '../types';

const CHALLENGE_TTL_SECONDS = 120; // 2-minute window

export async function handleRegisterChallenge(
  request: Request,
  env: Env
): Promise<Response> {
  const { userId } = await request.json<{ userId: string }>();
  if (!userId || typeof userId !== 'string') {
    return Response.json({ error: 'userId required' }, { status: 400 });
  }

  // Generate 32 cryptographically random bytes for the challenge
  const challengeBytes = crypto.getRandomValues(new Uint8Array(32));
  const challengeB64 = bufferToBase64url(challengeBytes);

  // Store challenge keyed by userId, expires in 2 minutes
  await env.CHALLENGES.put(
    `reg:${userId}`,
    JSON.stringify({ challenge: challengeB64, createdAt: Date.now() }),
    { expirationTtl: CHALLENGE_TTL_SECONDS }
  );

  return Response.json({
    challenge: challengeB64,
    rp: { name: 'Orchords App', id: new URL(request.url).hostname },
    user: {
      id: bufferToBase64url(new TextEncoder().encode(userId)),
      name: userId,
      displayName: userId,
    },
    pubKeyCredParams: [
      { type: 'public-key', alg: -7 },  // ES256
      { type: 'public-key', alg: -257 }, // RS256
    ],
    timeout: 60000,
    attestation: 'none',
    authenticatorSelection: {
      residentKey: 'preferred',
      userVerification: 'preferred',
    },
  });
}

function bufferToBase64url(buf: Uint8Array): string {
  return btoa(String.fromCharCode(...buf))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}
```

## Registration: Verify and Store Credential

```typescript
// src/handlers/webauthn-register-verify.ts
import type { Env } from '../types';

interface RegistrationBody {
  userId: string;
  credentialId: string;         // base64url
  clientDataJSON: string;       // base64url
  attestationObject: string;    // base64url (ignored for 'none' attestation)
  publicKeySpki: string;        // base64url SPKI — sent by client from getPublicKey()
}

export async function handleRegisterVerify(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<RegistrationBody>();

  // 1. Retrieve and consume the stored challenge
  const stored = await env.CHALLENGES.get(`reg:${body.userId}`, 'json') as
    | { challenge: string; createdAt: number }
    | null;

  if (!stored) {
    return Response.json({ error: 'challenge not found or expired' }, { status: 400 });
  }
  await env.CHALLENGES.delete(`reg:${body.userId}`);

  // 2. Parse clientDataJSON and verify type + challenge
  const clientData = JSON.parse(
    new TextDecoder().decode(base64urlToBuffer(body.clientDataJSON))
  ) as { type: string; challenge: string; origin: string };

  if (clientData.type !== 'webauthn.create') {
    return Response.json({ error: 'invalid clientData type' }, { status: 400 });
  }
  if (clientData.challenge !== stored.challenge) {
    return Response.json({ error: 'challenge mismatch' }, { status: 400 });
  }

  const expectedOrigin = new URL(request.url).origin;
  if (clientData.origin !== expectedOrigin) {
    return Response.json({ error: 'origin mismatch' }, { status: 400 });
  }

  // 3. Import the public key to confirm it is well-formed
  const spkiBytes = base64urlToBuffer(body.publicKeySpki);
  try {
    await crypto.subtle.importKey(
      'spki',
      spkiBytes,
      { name: 'ECDSA', namedCurve: 'P-256' },
      false,
      ['verify']
    );
  } catch {
    return Response.json({ error: 'invalid public key' }, { status: 400 });
  }

  // 4. Persist credential in D1
  await env.DB.prepare(
    `INSERT INTO webauthn_credentials
       (id, user_id, public_key_spki, sign_count, created_at)
     VALUES (?, ?, ?, 0, ?)`
  )
    .bind(body.credentialId, body.userId, body.publicKeySpki, Date.now())
    .run();

  return Response.json({ registered: true });
}

function base64urlToBuffer(b64: string): Uint8Array {
  const padded = b64.replace(/-/g, '+').replace(/_/g, '/') +
    '=='.slice(0, (4 - (b64.length % 4)) % 4);
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}
```

## Authentication: Verify Assertion

```typescript
// src/handlers/webauthn-auth-verify.ts
import type { Env } from '../types';

interface AssertionBody {
  userId: string;
  credentialId: string;
  clientDataJSON: string;    // base64url
  authenticatorData: string; // base64url
  signature: string;         // base64url DER-encoded
}

export async function handleAuthVerify(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<AssertionBody>();

  // 1. Consume stored challenge
  const stored = await env.CHALLENGES.get(`auth:${body.userId}`, 'json') as
    | { challenge: string }
    | null;
  if (!stored) {
    return Response.json({ error: 'challenge expired' }, { status: 400 });
  }
  await env.CHALLENGES.delete(`auth:${body.userId}`);

  // 2. Verify clientDataJSON
  const clientData = JSON.parse(
    new TextDecoder().decode(base64urlToBuffer(body.clientDataJSON))
  ) as { type: string; challenge: string; origin: string };

  if (clientData.type !== 'webauthn.get') {
    return Response.json({ error: 'invalid type' }, { status: 400 });
  }
  if (clientData.challenge !== stored.challenge) {
    return Response.json({ error: 'challenge mismatch' }, { status: 400 });
  }

  // 3. Load credential from D1
  const row = await env.DB.prepare(
    'SELECT public_key_spki, sign_count FROM webauthn_credentials WHERE id = ? AND user_id = ?'
  )
    .bind(body.credentialId, body.userId)
    .first<{ public_key_spki: string; sign_count: number }>();

  if (!row) {
    return Response.json({ error: 'credential not found' }, { status: 401 });
  }

  // 4. Reconstruct signed data: authData || SHA-256(clientDataJSON)
  const authDataBytes = base64urlToBuffer(body.authenticatorData);
  const clientDataHash = await crypto.subtle.digest(
    'SHA-256',
    base64urlToBuffer(body.clientDataJSON)
  );
  const signedData = new Uint8Array(authDataBytes.length + 32);
  signedData.set(authDataBytes, 0);
  signedData.set(new Uint8Array(clientDataHash), authDataBytes.length);

  // 5. Import stored public key and verify signature
  const publicKey = await crypto.subtle.importKey(
    'spki',
    base64urlToBuffer(row.public_key_spki),
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['verify']
  );

  const valid = await crypto.subtle.verify(
    { name: 'ECDSA', hash: 'SHA-256' },
    publicKey,
    base64urlToBuffer(body.signature),
    signedData
  );

  if (!valid) {
    return Response.json({ error: 'signature invalid' }, { status: 401 });
  }

  // 6. Update sign count (replay attack mitigation)
  const newSignCount = row.sign_count + 1;
  await env.DB.prepare(
    'UPDATE webauthn_credentials SET sign_count = ? WHERE id = ?'
  ).bind(newSignCount, body.credentialId).run();

  return Response.json({ authenticated: true, userId: body.userId });
}

function base64urlToBuffer(b64: string): Uint8Array {
  const padded = b64.replace(/-/g, '+').replace(/_/g, '/') +
    '=='.slice(0, (4 - (b64.length % 4)) % 4);
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}
```

## Anti-patterns

- **Storing challenge in a cookie or response body** — the challenge must be server-side only; KV with a TTL is correct.
- **Skipping origin verification** — always compare `clientData.origin` to the request origin; omitting this enables cross-origin replay.
- **Not incrementing or checking sign count** — a decreasing sign count signals a cloned authenticator; reject or alert.
- **Using `atob`/`btoa` for binary comparison** — always use `Uint8Array` and `crypto.subtle` for constant-time operations.
- **Storing the raw private key** — the private key never leaves the device; only the SPKI public key goes server-side.

## Gotchas

- `crypto.subtle.verify` for ECDSA expects the signature in IEEE P1363 format on some runtimes but DER on others. Browsers send DER; convert if needed.
- KV `expirationTtl` minimum is 60 seconds; set challenges to at least 60 s even for tighter UX.
- D1 `TEXT` stores base64url strings without padding; strip padding consistently on both encode and decode paths.
- `importKey` with `extractable: false` prevents the key material from being exported later — use it for production keys.

## Verification

```bash
# 1. Unit-test the crypto helpers
npx vitest run src/handlers/webauthn-register-verify.test.ts

# 2. Integration test with a virtual authenticator (Playwright)
npx playwright test tests/passkey.spec.ts --headed

# 3. Confirm D1 rows after a test registration
wrangler d1 execute app-db \
  --command "SELECT id, user_id, sign_count FROM webauthn_credentials LIMIT 5;"

# 4. Confirm KV challenge is deleted after verification
wrangler kv key get --namespace-id=<id> "reg:testuser"
# Expected: null / key not found
```

## Related

- `workers-session-fixation-prevention.md` — regenerate session after passkey login
- `workers-clickjacking-x-frame-options.md` — protect the registration page
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- Cloudflare KV docs: https://developers.cloudflare.com/kv/

## Sources

- W3C WebAuthn Level 3: https://www.w3.org/TR/webauthn-3/
- MDN Web Crypto API: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto
- Cloudflare Workers Runtime APIs: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
