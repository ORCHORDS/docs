# Passkey / WebAuthn Authentication for Mobile via Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Mobile apps that rely on username/password login are vulnerable to credential stuffing and phishing. Teams want to offer biometric authentication (Face ID, Touch ID, fingerprint) backed by hardware-bound passkeys without managing a dedicated auth server. The Workers platform must issue JWTs after verifying WebAuthn attestation and assertion.

---

## Context
WebAuthn splits registration and authentication into a two-step challenge–response flow. During registration the client requests a challenge from the server, the device generates a key pair, and the server verifies the attestation. During login the server issues a new challenge, the device signs it with the private key, and the server verifies the assertion before issuing a JWT. Cloudflare Workers KV is used to store challenges with a 5-minute TTL, preventing replay attacks. Credential public keys and metadata are stored in D1 for durability. The `@simplewebauthn/server` library handles the cryptographic verification so no raw WebAuthn parsing is needed.

---

## Section 1 — Wrangler Config & D1 Schema

```toml
# wrangler.toml
name = "webauthn-worker"
compatibility_date = "2025-06-01"

[[kv_namespaces]]
binding = "CHALLENGES"
id = "<YOUR_KV_NAMESPACE_ID>"

[[d1_databases]]
binding = "DB"
database_name = "auth_db"
database_id = "<YOUR_D1_DATABASE_ID>"

[vars]
RP_ID = "example.com"
RP_NAME = "Example App"
JWT_SECRET = "<rotate-via-secret-store>"
CHALLENGE_TTL_SECONDS = "300"
```

```bash
npx wrangler d1 execute auth_db --command "
CREATE TABLE IF NOT EXISTS users (
  id          TEXT PRIMARY KEY,
  username    TEXT UNIQUE NOT NULL,
  created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS credentials (
  id                    TEXT PRIMARY KEY,
  user_id               TEXT NOT NULL REFERENCES users(id),
  public_key            TEXT NOT NULL,
  counter               INTEGER NOT NULL DEFAULT 0,
  transports            TEXT,
  created_at            INTEGER NOT NULL,
  last_used_at          INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cred_user ON credentials(user_id);
"
```

---

## Section 2 — Workers Implementation

```typescript
// src/webauthn-worker.ts
import {
  generateRegistrationOptions,
  verifyRegistrationResponse,
  generateAuthenticationOptions,
  verifyAuthenticationResponse,
  type VerifiedRegistrationResponse,
} from '@simplewebauthn/server';
import { isoBase64URL } from '@simplewebauthn/server/helpers';

export interface Env {
  CHALLENGES: KVNamespace;
  DB: D1Database;
  RP_ID: string;
  RP_NAME: string;
  JWT_SECRET: string;
  CHALLENGE_TTL_SECONDS: string;
}

type StoredChallenge = {
  challenge: string;
  userId: string;
};

// Minimal JWT — replace with jose or CF Workers JWT binding in production
async function signJWT(payload: Record<string, unknown>, secret: string): Promise<string> {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = btoa(JSON.stringify({ ...payload, iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 3600 }));
  const data = `${header}.${body}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(data));
  return `${data}.${btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')}`;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(req.url);
    const ttl = Number(env.CHALLENGE_TTL_SECONDS);

    // --- POST /auth/register/begin ---
    if (req.method === 'POST' && pathname === '/auth/register/begin') {
      const { userId, username } = await req.json<{ userId: string; username: string }>();

      const options = await generateRegistrationOptions({
        rpName: env.RP_NAME,
        rpID: env.RP_ID,
        userID: isoBase64URL.fromString(userId),
        userName: username,
        attestationType: 'none',
        authenticatorSelection: {
          residentKey: 'preferred',
          userVerification: 'preferred',
        },
      });

      // Store challenge in KV with TTL
      const stored: StoredChallenge = { challenge: options.challenge, userId };
      await env.CHALLENGES.put(
        `reg:${userId}`,
        JSON.stringify(stored),
        { expirationTtl: ttl },
      );

      // Ensure user row exists
      await env.DB
        .prepare(
          `INSERT OR IGNORE INTO users (id, username, created_at) VALUES (?, ?, ?)`,
        )
        .bind(userId, username, Date.now())
        .run();

      return Response.json(options);
    }

    // --- POST /auth/register/complete ---
    if (req.method === 'POST' && pathname === '/auth/register/complete') {
      const { userId, response } = await req.json<{ userId: string; response: unknown }>();

      const raw = await env.CHALLENGES.get(`reg:${userId}`);
      if (!raw) return Response.json({ error: 'Challenge expired or not found' }, { status: 400 });

      const { challenge } = JSON.parse(raw) as StoredChallenge;
      await env.CHALLENGES.delete(`reg:${userId}`);

      let verification: VerifiedRegistrationResponse;
      try {
        verification = await verifyRegistrationResponse({
          response: response as any,
          expectedChallenge: challenge,
          expectedOrigin: `https://${env.RP_ID}`,
          expectedRPID: env.RP_ID,
        });
      } catch (e) {
        return Response.json({ error: String(e) }, { status: 400 });
      }

      if (!verification.verified || !verification.registrationInfo) {
        return Response.json({ error: 'Verification failed' }, { status: 400 });
      }

      const { credential } = verification.registrationInfo;
      await env.DB
        .prepare(
          `INSERT INTO credentials (id, user_id, public_key, counter, transports, created_at)
           VALUES (?, ?, ?, ?, ?, ?)`,
        )
        .bind(
          isoBase64URL.fromBuffer(credential.id),
          userId,
          isoBase64URL.fromBuffer(credential.publicKey),
          credential.counter,
          JSON.stringify(credential.transports ?? []),
          Date.now(),
        )
        .run();

      return Response.json({ verified: true });
    }

    // --- POST /auth/login/begin ---
    if (req.method === 'POST' && pathname === '/auth/login/begin') {
      const { userId } = await req.json<{ userId: string }>();

      const rows = await env.DB
        .prepare('SELECT id, transports FROM credentials WHERE user_id = ?')
        .bind(userId)
        .all<{ id: string; transports: string }>();

      const allowCredentials = rows.results.map(r => ({
        id: r.id,
        transports: JSON.parse(r.transports) as AuthenticatorTransport[],
      }));

      const options = await generateAuthenticationOptions({
        rpID: env.RP_ID,
        allowCredentials,
        userVerification: 'preferred',
      });

      const stored: StoredChallenge = { challenge: options.challenge, userId };
      await env.CHALLENGES.put(
        `auth:${userId}`,
        JSON.stringify(stored),
        { expirationTtl: ttl },
      );

      return Response.json(options);
    }

    // --- POST /auth/login/complete ---
    if (req.method === 'POST' && pathname === '/auth/login/complete') {
      const { userId, response } = await req.json<{ userId: string; response: unknown }>();

      const raw = await env.CHALLENGES.get(`auth:${userId}`);
      if (!raw) return Response.json({ error: 'Challenge expired' }, { status: 400 });
      const { challenge } = JSON.parse(raw) as StoredChallenge;
      await env.CHALLENGES.delete(`auth:${userId}`);

      const res = response as any;
      const credId = res.id as string;

      const credRow = await env.DB
        .prepare('SELECT * FROM credentials WHERE id = ? AND user_id = ?')
        .bind(credId, userId)
        .first<{ id: string; public_key: string; counter: number; transports: string }>();

      if (!credRow) return Response.json({ error: 'Credential not found' }, { status: 404 });

      let verification;
      try {
        verification = await verifyAuthenticationResponse({
          response: res,
          expectedChallenge: challenge,
          expectedOrigin: `https://${env.RP_ID}`,
          expectedRPID: env.RP_ID,
          credential: {
            id: credRow.id,
            publicKey: isoBase64URL.toBuffer(credRow.public_key),
            counter: credRow.counter,
            transports: JSON.parse(credRow.transports),
          },
        });
      } catch (e) {
        return Response.json({ error: String(e) }, { status: 400 });
      }

      if (!verification.verified) return Response.json({ error: 'Assertion failed' }, { status: 401 });

      // Update counter (prevents replay)
      await env.DB
        .prepare('UPDATE credentials SET counter=?, last_used_at=? WHERE id=?')
        .bind(verification.authenticationInfo.newCounter, Date.now(), credId)
        .run();

      const jwt = await signJWT({ sub: userId, credId }, env.JWT_SECRET);
      return Response.json({ verified: true, jwt });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

---

## Section 3 — React Native (Expo) Client Flow

```typescript
// src/auth/passkey.ts — uses react-native-passkey
import { Passkey } from 'react-native-passkey';

const WORKERS_URL = process.env.CF_WORKERS_BASE_URL ?? '';

export async function registerPasskey(userId: string, username: string) {
  const options = await fetch(`${WORKERS_URL}/auth/register/begin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, username }),
  }).then(r => r.json());

  const response = await Passkey.create(options);

  const result = await fetch(`${WORKERS_URL}/auth/register/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, response }),
  }).then(r => r.json());

  if (!result.verified) throw new Error('Registration failed');
  return result;
}

export async function loginWithPasskey(userId: string): Promise<string> {
  const options = await fetch(`${WORKERS_URL}/auth/login/begin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId }),
  }).then(r => r.json());

  const response = await Passkey.get(options);

  const result = await fetch(`${WORKERS_URL}/auth/login/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, response }),
  }).then(r => r.json());

  if (!result.verified) throw new Error('Authentication failed');
  return result.jwt;
}
```

---

## Anti-patterns
- **Reusing the same challenge across requests** — delete from KV immediately after verification; a race window where the same challenge can be used twice is a replay attack vector.
- **Storing `JWT_SECRET` in `[vars]` plaintext** — use `wrangler secret put JWT_SECRET` so it is encrypted at rest.
- **Skipping counter validation** — WebAuthn counters detect cloned authenticators; never skip the `newCounter > credRow.counter` check.

---

## Gotchas
- `react-native-passkey` requires iOS 16+ and Android API 28+; provide a fallback login method for older devices.
- The `expectedOrigin` for a native app using the Digital Asset Links / Associated Domains entitlement differs from a web origin — verify the `rpId` and origin match your app's bundle ID scheme.
- KV eventual consistency means a `get` immediately after a `put` might miss the value in a different region; the 5-minute TTL window provides sufficient buffer in practice.

---

## Verification

```bash
# Begin registration
curl -X POST https://webauthn-worker.example.workers.dev/auth/register/begin \
  -H 'Content-Type: application/json' \
  -d '{"userId":"user-1","username":"alice"}'

# Inspect stored challenge in KV
npx wrangler kv key get --binding=CHALLENGES 'reg:user-1'

# Inspect credentials in D1
npx wrangler d1 execute auth_db --command "SELECT id, user_id, counter FROM credentials"
```

---

## Related
- `react-native-cloudflare-workers-api-client.md`
- `capacitor-workers-file-upload-r2.md`

---

## Sources
- SimpleWebAuthn Server — https://simplewebauthn.dev/docs/packages/server
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- WebAuthn Spec — https://www.w3.org/TR/webauthn-3/
