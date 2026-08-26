# WebAuthn Passkey Implementation with Workers and D1 Credential Storage

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You want to replace password authentication with passkeys (FIDO2 / WebAuthn) while
keeping your backend fully serverless on Cloudflare Workers with D1. Most WebAuthn
guides assume Node.js with a traditional database; the Workers runtime lacks some Node
built-ins, and D1's SQLite dialect needs schema considerations for binary COSE key
material. This article covers the full registration and authentication ceremony
implemented as Workers handlers, credential storage in D1, and the security properties
that differ between platform (device-bound) and cross-platform (roaming) authenticators.

## Context

WebAuthn is a W3C standard that uses public-key cryptography to authenticate users.
The authenticator (phone biometrics, hardware key) generates an asymmetric key pair.
The private key never leaves the device; the relying party (RP) stores the public key
(credential) in D1. Authentication proves possession of the private key via a signature
over a challenge without transmitting the private key or a password.

**Security properties**:
- Phishing-resistant: the credential is bound to the exact RP ID (domain), so a
  phishing site on a different domain cannot use the credential.
- Replay-resistant: each ceremony uses a fresh random challenge signed by the server
  and consumed once.
- No shared secret: the server stores only a public key; a D1 database breach exposes
  no usable credentials.

**Attack vectors addressed**:
- Password credential stuffing (no password to stuff).
- Phishing (RP ID binding).
- Man-in-the-middle token theft (the signed challenge includes the TLS channel binding
  hash when `tokenBinding` is in use, though this is optional).
- Credential database breach (public keys are safe to expose).

**Authenticator types**:
- **Platform**: biometric sensor + secure enclave built into the device (Touch ID,
  Face ID, Windows Hello, Android fingerprint). Keys are device-bound and do not sync.
  With the `residentKey: required` option and a passkey-capable platform, the OS may
  sync via iCloud Keychain / Google Password Manager — these are called **discoverable
  credentials** or **passkeys**.
- **Cross-platform (roaming)**: hardware security key (YubiKey, etc.). Not synced.
  Higher assurance tier for admin/privileged flows.

## D1 Schema

```sql
-- migrations/0020_webauthn_credentials.sql

CREATE TABLE IF NOT EXISTS webauthn_credentials (
  -- Opaque, globally unique credential identifier issued by the authenticator
  credential_id       TEXT      NOT NULL PRIMARY KEY,  -- base64url-encoded
  user_id             TEXT      NOT NULL,
  -- Public key in COSE format, stored as base64url-encoded CBOR bytes
  public_key_cose     TEXT      NOT NULL,
  -- COSE algorithm identifier (e.g. -7 for ES256, -257 for RS256)
  cose_alg            INTEGER   NOT NULL,
  -- Replay protection: monotonically increasing per authenticator
  sign_count          INTEGER   NOT NULL DEFAULT 0,
  -- Metadata
  aaguid              TEXT      NOT NULL DEFAULT '',   -- authenticator model GUID
  is_backup_eligible  INTEGER   NOT NULL DEFAULT 0,   -- 1 = passkey (syncable)
  is_backed_up        INTEGER   NOT NULL DEFAULT 0,   -- 1 = currently synced
  transports          TEXT      NOT NULL DEFAULT '[]', -- JSON array
  created_at          TEXT      NOT NULL DEFAULT (datetime('now')),
  last_used_at        TEXT,
  friendly_name       TEXT                            -- user-assigned label
);

CREATE INDEX IF NOT EXISTS idx_wac_user ON webauthn_credentials(user_id);

-- One-time-use challenge store (TTL enforced at application layer)
CREATE TABLE IF NOT EXISTS webauthn_challenges (
  challenge           TEXT    NOT NULL PRIMARY KEY,  -- base64url random bytes
  user_id             TEXT,                          -- NULL for discoverable login
  ceremony_type       TEXT    NOT NULL,              -- 'registration' | 'authentication'
  expires_at          INTEGER NOT NULL,              -- Unix seconds
  created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

## Registration Ceremony

### Step 1: Generate and Store Challenge (GET /auth/passkey/register/begin)

```typescript
import { base64url } from 'jose'; // or any base64url encoder

export async function beginRegistration(
  request: Request,
  env: Env,
  userId: string,
  userDisplayName: string,
): Promise<Response> {
  // Generate a cryptographically random challenge (≥ 16 bytes, 32 recommended)
  const challengeBytes = crypto.getRandomValues(new Uint8Array(32));
  const challengeB64 = base64url.encode(challengeBytes);

  // Store challenge with a 5-minute TTL
  const expiresAt = Math.floor(Date.now() / 1000) + 300;
  await env.DB.prepare(
    `INSERT INTO webauthn_challenges (challenge, user_id, ceremony_type, expires_at)
     VALUES (?1, ?2, 'registration', ?3)`,
  )
    .bind(challengeB64, userId, expiresAt)
    .run();

  // Build PublicKeyCredentialCreationOptions
  const options = {
    challenge: challengeB64,
    rp: {
      name: env.RP_NAME,
      id: env.RP_ID,
    },
    user: {
      id: base64url.encode(new TextEncoder().encode(userId)),
      name: userDisplayName,
      displayName: userDisplayName,
    },
    pubKeyCredParams: [
      { type: 'public-key', alg: -7 },   // ES256  (preferred)
      { type: 'public-key', alg: -257 }, // RS256  (Windows Hello fallback)
      { type: 'public-key', alg: -8 },   // EdDSA  (hardware keys)
    ],
    authenticatorSelection: {
      residentKey: 'preferred',           // enable passkey sync when supported
      userVerification: 'preferred',      // biometric / PIN required
      authenticatorAttachment: undefined, // allow both platform and cross-platform
    },
    timeout: 300_000, // 5 minutes
    attestation: 'none', // 'direct' for enterprise, 'none' is simplest
  };

  return Response.json(options);
}
```

### Step 2: Verify and Store Credential (POST /auth/passkey/register/finish)

```typescript
import { decodeProtectedHeader, importSPKI, compactVerify } from 'jose';
import { decode as cborDecode } from 'cbor-x'; // lightweight CBOR for Workers

export async function finishRegistration(
  request: Request,
  env: Env,
  userId: string,
): Promise<Response> {
  const body = await request.json<{
    id: string;
    rawId: string;           // base64url
    response: {
      clientDataJSON: string;
      attestationObject: string;
    };
    transports?: string[];
  }>();

  // 1. Decode and verify clientDataJSON
  const clientData = JSON.parse(
    new TextDecoder().decode(base64url.decode(body.response.clientDataJSON)),
  );

  if (clientData.type !== 'webauthn.create') {
    return Response.json({ error: 'invalid_ceremony_type' }, { status: 400 });
  }

  if (clientData.origin !== `https://${env.RP_ID}`) {
    return Response.json({ error: 'origin_mismatch' }, { status: 400 });
  }

  // 2. Verify and consume challenge (replay prevention)
  const challenge = clientData.challenge;
  const now = Math.floor(Date.now() / 1000);
  const challengeRow = await env.DB.prepare(
    `SELECT * FROM webauthn_challenges
      WHERE challenge = ?1 AND user_id = ?2
        AND ceremony_type = 'registration' AND expires_at > ?3`,
  )
    .bind(challenge, userId, now)
    .first<{ challenge: string }>();

  if (!challengeRow) {
    return Response.json({ error: 'invalid_or_expired_challenge' }, { status: 400 });
  }

  // Delete challenge immediately — single use
  await env.DB.prepare(`DELETE FROM webauthn_challenges WHERE challenge = ?1`)
    .bind(challenge)
    .run();

  // 3. Decode attestationObject (CBOR)
  const attestationBytes = base64url.decode(body.response.attestationObject);
  const attestation = cborDecode(attestationBytes) as {
    fmt: string;
    authData: Uint8Array;
    attStmt: unknown;
  };

  // 4. Parse authData
  const authData = parseAuthenticatorData(attestation.authData);

  // Verify RP ID hash
  const rpIdHash = new Uint8Array(
    await crypto.subtle.digest('SHA-256', new TextEncoder().encode(env.RP_ID)),
  );
  if (!timingSafeEqual(rpIdHash, authData.rpIdHash)) {
    return Response.json({ error: 'rpid_hash_mismatch' }, { status: 400 });
  }

  // Verify user presence (UP) flag
  if (!(authData.flags & 0x01)) {
    return Response.json({ error: 'user_presence_not_verified' }, { status: 400 });
  }

  // Verify user verification (UV) flag if required
  if (env.REQUIRE_USER_VERIFICATION && !(authData.flags & 0x04)) {
    return Response.json({ error: 'user_verification_required' }, { status: 400 });
  }

  // 5. Extract and store credential
  const credentialIdB64 = base64url.encode(authData.credentialId!);
  const publicKeyCoseB64 = base64url.encode(authData.credentialPublicKey!);

  // Check for duplicate credential ID
  const existing = await env.DB.prepare(
    `SELECT credential_id FROM webauthn_credentials WHERE credential_id = ?1`,
  )
    .bind(credentialIdB64)
    .first();

  if (existing) {
    return Response.json({ error: 'credential_already_registered' }, { status: 409 });
  }

  const BE = !!(authData.flags & 0x08); // backup eligible (passkey-capable)
  const BS = !!(authData.flags & 0x10); // currently backed up

  await env.DB.prepare(
    `INSERT INTO webauthn_credentials
       (credential_id, user_id, public_key_cose, cose_alg, sign_count,
        aaguid, is_backup_eligible, is_backed_up, transports)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)`,
  )
    .bind(
      credentialIdB64,
      userId,
      publicKeyCoseB64,
      authData.credentialPublicKeyAlg ?? -7,
      authData.signCount,
      authData.aaguid ? base64url.encode(authData.aaguid) : '',
      BE ? 1 : 0,
      BS ? 1 : 0,
      JSON.stringify(body.transports ?? []),
    )
    .run();

  return Response.json({ verified: true });
}
```

## Authentication Ceremony

```typescript
export async function beginAuthentication(
  request: Request,
  env: Env,
  userId?: string, // undefined for discoverable credential (usernameless) flow
): Promise<Response> {
  const challengeBytes = crypto.getRandomValues(new Uint8Array(32));
  const challengeB64 = base64url.encode(challengeBytes);
  const expiresAt = Math.floor(Date.now() / 1000) + 300;

  await env.DB.prepare(
    `INSERT INTO webauthn_challenges (challenge, user_id, ceremony_type, expires_at)
     VALUES (?1, ?2, 'authentication', ?3)`,
  )
    .bind(challengeB64, userId ?? null, expiresAt)
    .run();

  // For known-user flows, populate allowCredentials
  let allowCredentials: { type: string; id: string; transports: string[] }[] = [];
  if (userId) {
    const creds = await env.DB.prepare(
      `SELECT credential_id, transports FROM webauthn_credentials WHERE user_id = ?1`,
    )
      .bind(userId)
      .all<{ credential_id: string; transports: string }>();

    allowCredentials = creds.results.map((c) => ({
      type: 'public-key',
      id: c.credential_id,
      transports: JSON.parse(c.transports),
    }));
  }

  return Response.json({
    challenge: challengeB64,
    rpId: env.RP_ID,
    allowCredentials,
    userVerification: 'preferred',
    timeout: 300_000,
  });
}

export async function finishAuthentication(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.json<{
    id: string;
    response: {
      clientDataJSON: string;
      authenticatorData: string;
      signature: string;
      userHandle?: string;
    };
  }>();

  // 1. Load credential from D1
  const credentialIdB64 = body.id;
  const cred = await env.DB.prepare(
    `SELECT * FROM webauthn_credentials WHERE credential_id = ?1`,
  )
    .bind(credentialIdB64)
    .first<{
      credential_id: string;
      user_id: string;
      public_key_cose: string;
      cose_alg: number;
      sign_count: number;
    }>();

  if (!cred) {
    return Response.json({ error: 'credential_not_found' }, { status: 400 });
  }

  // 2. Verify challenge
  const clientData = JSON.parse(
    new TextDecoder().decode(base64url.decode(body.response.clientDataJSON)),
  );
  if (clientData.type !== 'webauthn.get') {
    return Response.json({ error: 'invalid_ceremony_type' }, { status: 400 });
  }

  const now = Math.floor(Date.now() / 1000);
  const challengeRow = await env.DB.prepare(
    `SELECT challenge FROM webauthn_challenges
      WHERE challenge = ?1 AND ceremony_type = 'authentication' AND expires_at > ?2`,
  )
    .bind(clientData.challenge, now)
    .first();

  if (!challengeRow) {
    return Response.json({ error: 'invalid_or_expired_challenge' }, { status: 400 });
  }
  await env.DB.prepare(`DELETE FROM webauthn_challenges WHERE challenge = ?1`)
    .bind(clientData.challenge)
    .run();

  // 3. Verify signature over authData + clientDataJSONHash
  const authDataBytes = base64url.decode(body.response.authenticatorData);
  const clientDataHash = new Uint8Array(
    await crypto.subtle.digest(
      'SHA-256',
      base64url.decode(body.response.clientDataJSON),
    ),
  );
  const signedData = concatUint8Arrays(authDataBytes, clientDataHash);

  const publicKey = await importCosePublicKey(base64url.decode(cred.public_key_cose));
  const sigBytes = base64url.decode(body.response.signature);

  const valid = await verifySignature(publicKey, sigBytes, signedData, cred.cose_alg);
  if (!valid) {
    return Response.json({ error: 'invalid_signature' }, { status: 400 });
  }

  // 4. Check and update sign count (clone detection)
  const authData = parseAuthenticatorData(authDataBytes);
  if (authData.signCount !== 0 && authData.signCount <= cred.sign_count) {
    // Possible cloned authenticator — alert and reject
    await logSecurityEvent(env, {
      type: 'webauthn_sign_count_regression',
      credentialId: credentialIdB64,
      userId: cred.user_id,
      expected: cred.sign_count,
      received: authData.signCount,
    });
    return Response.json({ error: 'authenticator_clone_detected' }, { status: 400 });
  }

  await env.DB.prepare(
    `UPDATE webauthn_credentials
        SET sign_count = ?1, last_used_at = datetime('now')
      WHERE credential_id = ?2`,
  )
    .bind(authData.signCount, credentialIdB64)
    .run();

  // 5. Issue session token
  return Response.json({
    verified: true,
    userId: cred.user_id,
  });
}
```

## Mobile vs Web Considerations

- **Platform passkeys on mobile**: iOS Safari and Chrome for Android support passkeys
  that sync via iCloud Keychain / Google Password Manager. The `BE` flag in authData
  indicates the credential is backup-eligible; `BS` indicates it is currently synced.
  Track both in D1 to inform UX ("this passkey is synced to iCloud").
- **WebView caveats**: passkeys do not work in WKWebView (iOS) or WebView (Android)
  by default. Use `ASWebAuthenticationSession` on iOS or Custom Tabs on Android for
  a passkey flow embedded in a native shell. Alternatively, call a native WebAuthn API
  directly using the platform's FIDO2 APIs (Credential Manager on Android 14+).
- **`userHandle` in authentication response**: for discoverable credentials, the
  authenticator returns the `userHandle` (the `user.id` set during registration).
  Use it to look up the user before validating the credential.
- **Native Android Credential Manager**: Google's Credential Manager API provides a
  unified passkey and password flow. The RP must publish a Digital Asset Links file
  at `https://example.com/.well-known/assetlinks.json` to link the Android app to
  the RP ID.

## Anti-patterns

- **Storing challenges in KV without deletion**: consumed challenges must be deleted
  immediately. KV TTL expiry alone is not sufficient because it does not prevent a
  replay within the TTL window.
- **Not validating the `origin`**: an attacker serving the WebAuthn JS on a different
  origin (via XSS or phishing) would otherwise be able to register credentials
  against your RP. Always check `clientData.origin === 'https://' + RP_ID`.
- **Ignoring sign count**: passkey syncing means count can legitimately be 0 (synced
  credentials reset their counter). Accept `signCount === 0` as a non-counting
  authenticator, but alert on regressions where count > 0 then decreases.
- **Storing `credential_id` as binary BLOB in D1**: SQLite's D1 binding for BLOBs
  is available but base64url TEXT is more portable for debugging and exports.
- **Not limiting credentials per user**: a user could register thousands of passkeys,
  consuming D1 row quota and slowing credential lookup. Enforce a cap (e.g., 20
  credentials per user).

## Gotchas

- The `@simplewebauthn/server` package requires Node.js buffers and some APIs not
  available in Workers. Use a Workers-compatible CBOR library (`cbor-x` works in the
  edge runtime) and implement the verification steps manually as shown.
- Workers `crypto.subtle` does not support COSE key parsing natively. You must decode
  the CBOR-encoded COSE key structure and call `importKey` with the raw EC or RSA
  parameters.
- Attestation verification (`fmt: 'packed'`, `fmt: 'tpm'`, etc.) is complex and
  usually unnecessary unless you require enterprise attestation assurance. `none`
  attestation skips this entirely.
- D1's `INSERT … ON CONFLICT` is SQLite syntax; test your migrations with
  `wrangler d1 execute --local` before deploying.

## Verification

```bash
# Test registration flow with a software authenticator (e.g., using Playwright)
# or manually via the browser DevTools console:
# 1. GET /auth/passkey/register/begin — copy the challenge
# 2. navigator.credentials.create({publicKey: <options>}) — creates a credential
# 3. POST /auth/passkey/register/finish with the credential

# Check stored credential in D1
wrangler d1 execute my-db \
  --command "SELECT credential_id, user_id, cose_alg, sign_count, is_backup_eligible FROM webauthn_credentials"

# Verify challenge table is empty after ceremonies
wrangler d1 execute my-db --command "SELECT COUNT(*) FROM webauthn_challenges"
```

## Related

- `webauthn-passkey-flow.md`
- `webauthn-backup-eligibility-state-policy.md`
- `webauthn-credprotect-policy-negotiation.md`
- `webauthn-signal-api-credential-reconciliation.md`
- `sql-injection-prevention-d1-workers.md`
- `jwt-sliding-window-refresh-workers-kv.md`

## Sources

- WebAuthn Level 3 spec: https://www.w3.org/TR/webauthn-3/
- FIDO2 Server Requirements: https://fidoalliance.org/specs/fido-v2.2-rd-20230321/fido-client-to-authenticator-protocol-v2.2-rd-20230321.html
- Passkeys.dev (FIDO Alliance guidance): https://passkeys.dev/
- Android Credential Manager: https://developer.android.com/identity/sign-in/credential-manager
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- cbor-x (Workers-compatible CBOR): https://github.com/kriszyp/cbor-x
