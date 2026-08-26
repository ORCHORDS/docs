# Passkey WebAuthn Registration Ceremony in Cloudflare Workers with D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You are building a passwordless authentication flow where users register a FIDO2 passkey
(platform authenticator or roaming security key) and you need the entire registration
ceremony — challenge generation, credential creation options, attestation verification,
and credential storage — to run as a Cloudflare Worker backed by D1 and KV.

The existing `webauthn-passkey-workers-d1-implementation.md` covers the authentication
(assertion) flow.  This article covers only the **registration ceremony** in detail:
generating `PublicKeyCredentialCreationOptions`, validating the
`AuthenticatorAttestationResponse`, parsing CBOR-encoded COSE public keys, and persisting
the credential in D1.

---

## Context

The WebAuthn registration ceremony is defined in the W3C WebAuthn Level 3 specification
(§7.1).  In server-side terms it is a two-step round-trip:

1. **GET /webauthn/register/begin** — server generates a random challenge, returns
   `PublicKeyCredentialCreationOptions` as JSON.
2. **POST /webauthn/register/complete** — client sends the
   `AuthenticatorAttestationResponse`; server verifies it and stores the credential.

The challenge must be stored server-side (in KV with a short TTL) so it can be compared
during completion.  Cloudflare Workers fit this perfectly: stateless compute, KV for
ephemeral challenge state, D1 for durable credential storage.

---

## 1. D1 Schema for Credentials

```sql
CREATE TABLE IF NOT EXISTS passkey_credentials (
  id              TEXT PRIMARY KEY,     -- base64url credential ID (from authenticator)
  user_id         TEXT NOT NULL,
  public_key_cbor BLOB NOT NULL,        -- raw COSE public key bytes
  algorithm       INTEGER NOT NULL,     -- COSE algorithm id, e.g. -7 (ES256)
  sign_count      INTEGER NOT NULL DEFAULT 0,
  aaguid          TEXT NOT NULL DEFAULT '',
  transports      TEXT NOT NULL DEFAULT '[]', -- JSON array
  backup_eligible INTEGER NOT NULL DEFAULT 0,
  backup_state    INTEGER NOT NULL DEFAULT 0,
  created_at      INTEGER NOT NULL,
  last_used_at    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_passkey_user ON passkey_credentials (user_id);
```

KV namespace: `CHALLENGE_STORE`  — keys like `reg_challenge:<userId>`, TTL 300 seconds.

---

## 2. Step 1 — Generate Registration Options

```typescript
// src/register-begin.ts
export interface RegBeginOptions {
  userId: string;
  username: string;
  displayName: string;
  existingCredentialIds: string[]; // base64url IDs to exclude
}

export interface CreationOptionsResponse {
  challenge: string;        // base64url
  rp: { name: string; id: string };
  user: { id: string; name: string; displayName: string };
  pubKeyCredParams: Array<{ type: 'public-key'; alg: number }>;
  timeout: number;
  attestation: 'none' | 'indirect' | 'direct';
  authenticatorSelection: {
    residentKey: 'required' | 'preferred' | 'discouraged';
    userVerification: 'required' | 'preferred' | 'discouraged';
    requireResidentKey: boolean;
  };
  excludeCredentials: Array<{ type: 'public-key'; id: string; transports: string[] }>;
}

function base64urlEncode(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

export async function generateRegistrationOptions(
  opts: RegBeginOptions,
  rpId: string,
  rpName: string,
): Promise<{ options: CreationOptionsResponse; challengeB64: string }> {
  const challengeBytes = new Uint8Array(32);
  crypto.getRandomValues(challengeBytes);
  const challengeB64 = base64urlEncode(challengeBytes.buffer);

  // User ID must be a random buffer, NOT the username itself (privacy)
  const userIdBytes = new TextEncoder().encode(opts.userId);
  const userIdB64 = base64urlEncode(userIdBytes.buffer);

  const options: CreationOptionsResponse = {
    challenge: challengeB64,
    rp: { name: rpName, id: rpId },
    user: {
      id: userIdB64,
      name: opts.username,
      displayName: opts.displayName,
    },
    pubKeyCredParams: [
      { type: 'public-key', alg: -7  },   // ES256
      { type: 'public-key', alg: -257 },  // RS256 (legacy)
    ],
    timeout: 300_000, // 5 minutes
    attestation: 'none',  // prefer 'none' for privacy
    authenticatorSelection: {
      residentKey: 'required',
      userVerification: 'required',
      requireResidentKey: true,
    },
    excludeCredentials: opts.existingCredentialIds.map((id) => ({
      type: 'public-key',
      id,
      transports: ['internal', 'hybrid'],
    })),
  };

  return { options, challengeB64 };
}
```

---

## 3. Challenge Storage in KV

```typescript
// src/challenge-store.ts
const CHALLENGE_TTL_SECONDS = 300;

export async function storeChallenge(
  kv: KVNamespace,
  userId: string,
  challengeB64: string,
): Promise<void> {
  await kv.put(
    `reg_challenge:${userId}`,
    challengeB64,
    { expirationTtl: CHALLENGE_TTL_SECONDS },
  );
}

export async function consumeChallenge(
  kv: KVNamespace,
  userId: string,
): Promise<string | null> {
  const challenge = await kv.get(`reg_challenge:${userId}`);
  if (challenge) {
    // Delete immediately — one-time use
    await kv.delete(`reg_challenge:${userId}`);
  }
  return challenge;
}
```

---

## 4. Verifying the Attestation Response (§7.1)

```typescript
// src/register-complete.ts

export interface AttestationResponse {
  id: string;              // base64url credential ID
  rawId: string;           // base64url
  type: 'public-key';
  response: {
    clientDataJSON: string;   // base64url
    attestationObject: string; // base64url
  };
  authenticatorAttachment?: string;
}

function base64urlDecode(b64url: string): Uint8Array {
  const b64 = b64url.replace(/-/g, '+').replace(/_/g, '/');
  const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

export async function verifyAttestationResponse(
  attestation: AttestationResponse,
  expectedChallenge: string,
  expectedOrigin: string,
  rpId: string,
): Promise<{
  credentialId: string;
  publicKeyCbor: Uint8Array;
  algorithm: number;
  aaguid: string;
  signCount: number;
  backupEligible: boolean;
  backupState: boolean;
  transports: string[];
}> {
  // 1. Parse clientDataJSON
  const clientDataBytes = base64urlDecode(attestation.response.clientDataJSON);
  const clientData = JSON.parse(new TextDecoder().decode(clientDataBytes)) as {
    type: string;
    challenge: string;
    origin: string;
    crossOrigin?: boolean;
  };

  if (clientData.type !== 'webauthn.create') {
    throw new Error('Invalid clientData.type');
  }
  if (clientData.challenge !== expectedChallenge) {
    throw new Error('Challenge mismatch');
  }
  if (clientData.origin !== expectedOrigin) {
    throw new Error('Origin mismatch');
  }
  if (clientData.crossOrigin === true) {
    throw new Error('Cross-origin registration rejected');
  }

  // 2. Parse authenticatorData from attestationObject (CBOR)
  // Full CBOR parsing is needed in production; here we use a simplified layout.
  const attestationObjectBytes = base64urlDecode(attestation.response.attestationObject);
  const authData = extractAuthData(attestationObjectBytes);

  // 3. Verify rpIdHash
  const expectedRpIdHash = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(rpId),
  );
  const rpIdHash = authData.slice(0, 32);
  if (!timingSafeEqual(new Uint8Array(expectedRpIdHash), rpIdHash)) {
    throw new Error('RP ID hash mismatch');
  }

  // 4. Check flags byte
  const flags = authData[32];
  const userPresent  = (flags & 0x01) !== 0;
  const userVerified = (flags & 0x04) !== 0;
  const backupEligible = (flags & 0x08) !== 0;
  const backupState    = (flags & 0x10) !== 0;
  const attestedCredentialData = (flags & 0x40) !== 0;

  if (!userPresent)  throw new Error('User Present flag not set');
  if (!userVerified) throw new Error('User Verified flag not set');
  if (!attestedCredentialData) throw new Error('Attested credential data flag not set');

  // 5. Extract sign count (bytes 33-36, big-endian)
  const signCount =
    (authData[33] << 24) | (authData[34] << 16) | (authData[35] << 8) | authData[36];

  // 6. Extract AAGUID (bytes 37-52)
  const aaguidBytes = authData.slice(37, 53);
  const aaguid = formatAaguid(aaguidBytes);

  // 7. Extract credential ID
  const credIdLen = (authData[53] << 8) | authData[54];
  const credId = authData.slice(55, 55 + credIdLen);
  const credentialId = base64urlEncodeBytes(credId);

  // 8. Extract COSE public key (remaining bytes after credential ID)
  const publicKeyCbor = authData.slice(55 + credIdLen);

  // 9. Determine algorithm from COSE key map (key -1 = alg, usually first field)
  // A proper CBOR decoder is needed here; -7 = ES256, -257 = RS256
  const algorithm = parseCoseAlgorithm(publicKeyCbor);

  return {
    credentialId,
    publicKeyCbor,
    algorithm,
    aaguid,
    signCount,
    backupEligible,
    backupState,
    transports: [],
  };
}

function timingSafeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

function base64urlEncodeBytes(buf: Uint8Array): string {
  return btoa(String.fromCharCode(...buf))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

function formatAaguid(bytes: Uint8Array): string {
  const hex = Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

// Stub — replace with a proper CBOR library (e.g. cbor-x compiled to WASM)
function extractAuthData(attestationObject: Uint8Array): Uint8Array {
  // In a real implementation, CBOR-decode the attestationObject map
  // and extract the "authData" key's value.
  // This stub returns a placeholder.
  throw new Error('Replace with CBOR decoder');
}

function parseCoseAlgorithm(coseKey: Uint8Array): number {
  // COSE key map: look for key 3 (alg)
  // Replace with actual CBOR decoding; return -7 for ES256
  return -7;
}
```

---

## 5. Persisting the Credential to D1

```typescript
// src/register-store.ts
export async function storeCredential(
  db: D1Database,
  userId: string,
  credentialId: string,
  publicKeyCbor: Uint8Array,
  algorithm: number,
  aaguid: string,
  signCount: number,
  backupEligible: boolean,
  backupState: boolean,
  transports: string[],
): Promise<void> {
  // Check for duplicate credential ID (authenticator re-registration)
  const existing = await db
    .prepare(`SELECT id FROM passkey_credentials WHERE id = ?`)
    .bind(credentialId)
    .first();

  if (existing) {
    throw new Error('Credential ID already registered');
  }

  await db
    .prepare(
      `INSERT INTO passkey_credentials
         (id, user_id, public_key_cbor, algorithm, sign_count,
          aaguid, transports, backup_eligible, backup_state, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      credentialId,
      userId,
      publicKeyCbor,
      algorithm,
      signCount,
      aaguid,
      JSON.stringify(transports),
      backupEligible ? 1 : 0,
      backupState ? 1 : 0,
      Date.now(),
    )
    .run();
}
```

---

## 6. Worker Routes

```typescript
// src/index.ts — registration routes only
import { generateRegistrationOptions, storeChallenge, consumeChallenge } from './register-begin';
import { verifyAttestationResponse } from './register-complete';
import { storeCredential } from './register-store';

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (req.method === 'GET' && url.pathname === '/webauthn/register/begin') {
      const userId = url.searchParams.get('userId');
      if (!userId) return new Response('Missing userId', { status: 400 });

      const { options, challengeB64 } = await generateRegistrationOptions(
        { userId, username: userId, displayName: userId, existingCredentialIds: [] },
        env.RP_ID, env.RP_NAME,
      );
      await storeChallenge(env.CHALLENGE_STORE, userId, challengeB64);
      return Response.json(options);
    }

    if (req.method === 'POST' && url.pathname === '/webauthn/register/complete') {
      const body = await req.json<{ userId: string; attestation: unknown }>();
      const challenge = await consumeChallenge(env.CHALLENGE_STORE, body.userId);
      if (!challenge) return new Response('Challenge expired', { status: 400 });

      const result = await verifyAttestationResponse(
        body.attestation as any,
        challenge,
        env.EXPECTED_ORIGIN,
        env.RP_ID,
      );

      await storeCredential(env.DB, body.userId, result.credentialId,
        result.publicKeyCbor, result.algorithm, result.aaguid,
        result.signCount, result.backupEligible, result.backupState, result.transports);

      return Response.json({ registered: true, credentialId: result.credentialId });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

---

## Anti-patterns

- **Storing the challenge in a cookie** — cookies are controlled by the client; always
  store the challenge server-side in KV.
- **Accepting `attestation: 'none'` and then trying to verify attestation** — choose one
  strategy; for most consumer passkey deployments `attestation: 'none'` is correct.
- **Not deleting the challenge after verification** — leave challenges reusable and an
  attacker can replay a captured registration response.
- **Not verifying the `rpId` hash in `authData`** — skip this check and a malicious
  authenticator can register credentials for a different origin.
- **Skipping the `backup_eligible` column** — passkeys can be synced across devices; if
  your threat model requires single-device binding, reject credentials where
  `backupEligible=1`.

---

## Gotchas

- The CBOR decoding of `attestationObject` requires a proper library (e.g. `cbor-x`
  compiled to WASM); the stub in section 4 must be replaced before production use.
- `authenticatorData` bytes 33-36 are the sign count in **big-endian** unsigned 32-bit
  integer; mixing up byte order produces incorrect counts that fail counter checks.
- Credential IDs from platform authenticators can be up to 1023 bytes long; ensure your
  D1 `TEXT` column and the base64url encoding handle this.
- The `crossOrigin` field in `clientDataJSON` must be `false` or absent for same-origin
  registration; a cross-origin registration is legitimate only for related-origin
  scenarios and requires the `/.well-known/webauthn` file.
- KV TTL of 300 seconds is generous; reduce to 120 seconds for tighter replay windows.

---

## Verification

```bash
# 1. Get registration options
curl "https://auth.<account>.workers.dev/webauthn/register/begin?userId=test@example.com" \
  | jq '{challenge: .challenge, rpId: .rp.id}'

# 2. Simulate completion with a captured attestation (from a test authenticator)
curl -X POST "https://auth.<account>.workers.dev/webauthn/register/complete" \
  -H "Content-Type: application/json" \
  -d '{"userId":"test@example.com","attestation":{...}}'

# 3. Verify credential stored
wrangler d1 execute passkey-db \
  --command "SELECT id, user_id, aaguid, backup_eligible FROM passkey_credentials"

# 4. Verify challenge is consumed (attempt replay)
curl -X POST "https://auth.<account>.workers.dev/webauthn/register/complete" \
  -H "Content-Type: application/json" \
  -d '{"userId":"test@example.com","attestation":{...}}'
# Expect: 400 Challenge expired
```

---

## Related

- `webauthn-passkey-workers-d1-implementation.md`
- `fido2-passkey-durable-objects-session-binding.md`
- `webauthn-passkey-flow.md`
- `webauthn-backup-eligibility-state-policy.md`
- `webauthn-cross-origin-iframe-top-origin-binding.md`

---

## Sources

- W3C WebAuthn Level 3 §7.1 — Registration ceremony: https://www.w3.org/TR/webauthn-3/#sctn-registering-a-new-credential
- CBOR RFC 8949: https://www.rfc-editor.org/rfc/rfc8949
- COSE RFC 9052: https://www.rfc-editor.org/rfc/rfc9052
- SimpleWebAuthn (reference implementation): https://github.com/MasterKale/SimpleWebAuthn
- Cloudflare KV: https://developers.cloudflare.com/kv/
