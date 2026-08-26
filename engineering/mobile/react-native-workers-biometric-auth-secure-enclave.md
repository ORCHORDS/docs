# React Native Biometric Auth with Secure Enclave and Cloudflare Workers Challenge–Response

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

You want to authenticate React Native users with Face ID / fingerprint / device biometrics without storing a password or long-lived bearer token that can be exfiltrated from device storage. The server should issue a cryptographic challenge, the device signs it inside the Secure Enclave (iOS) or StrongBox (Android), and the Worker verifies the signature. This is distinct from WebAuthn: you are signing a custom challenge with a key pair stored in the platform's hardware security module, using `react-native-keychain` for key management and a Workers endpoint for challenge issuance and signature verification.

---

## Context

Both iOS Secure Enclave and Android StrongBox support EC P-256 or P-384 key pairs where the private key never leaves the hardware. `react-native-keychain` exposes this via `ACCESS_CONTROL.BIOMETRY_CURRENT_SET` on iOS and `SECURITY_LEVEL.SECURE_HARDWARE` on Android. The flow is:

1. **Register** — generate a key pair on-device, send the public key to the Worker, which stores it in D1 linked to the user.
2. **Authenticate** — client requests a nonce from the Worker, signs it with the private key (triggers biometric prompt), sends the signature; Worker verifies with the stored public key.

Challenges are single-use nonces stored in KV with a 60-second TTL.

```toml
# wrangler.toml
name = "biometric-auth-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "CHALLENGES"
id = "YOUR_KV_NAMESPACE_ID"

[[d1_databases]]
binding = "DB"
database_name = "auth"
database_id = "YOUR_D1_DATABASE_ID"
```

---

## 1. D1 Schema

```sql
-- migrations/0001_biometric_keys.sql
CREATE TABLE IF NOT EXISTS biometric_keys (
  user_id     TEXT NOT NULL,
  device_id   TEXT NOT NULL,
  public_key  TEXT NOT NULL,  -- Base64url-encoded DER SubjectPublicKeyInfo
  algorithm   TEXT NOT NULL DEFAULT 'ES256',
  created_at  INTEGER NOT NULL,
  PRIMARY KEY (user_id, device_id)
);
```

---

## 2. Worker: Registration and Challenge Endpoints

```typescript
// src/index.ts
export interface Env {
  CHALLENGES: KVNamespace;
  DB: D1Database;
}

function base64urlDecode(s: string): ArrayBuffer {
  const base64 = s.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const { pathname } = url;

    // POST /auth/register  — store a device's public key
    if (request.method === "POST" && pathname === "/auth/register") {
      const { userId, deviceId, publicKey } = await request.json<{
        userId: string;
        deviceId: string;
        publicKey: string; // base64url DER
      }>();

      await env.DB.prepare(
        `INSERT OR REPLACE INTO biometric_keys (user_id, device_id, public_key, algorithm, created_at)
         VALUES (?, ?, ?, 'ES256', ?)`,
      )
        .bind(userId, deviceId, publicKey, Date.now())
        .run();

      return new Response(JSON.stringify({ ok: true }), {
        headers: { "content-type": "application/json" },
      });
    }

    // GET /auth/challenge?userId=…&deviceId=…
    if (request.method === "GET" && pathname === "/auth/challenge") {
      const userId = url.searchParams.get("userId");
      const deviceId = url.searchParams.get("deviceId");
      if (!userId || !deviceId) return new Response("Bad request", { status: 400 });

      const nonce = crypto.randomUUID();
      const key = `challenge:${userId}:${deviceId}:${nonce}`;
      await env.CHALLENGES.put(key, "1", { expirationTtl: 60 });

      return new Response(JSON.stringify({ nonce }), {
        headers: { "content-type": "application/json" },
      });
    }

    // POST /auth/verify  — verify signed nonce, return session token
    if (request.method === "POST" && pathname === "/auth/verify") {
      const { userId, deviceId, nonce, signature } = await request.json<{
        userId: string;
        deviceId: string;
        nonce: string;      // UUID from /auth/challenge
        signature: string;  // base64url DER signature over UTF-8 nonce bytes
      }>();

      // 1. Consume the nonce (single-use)
      const challengeKey = `challenge:${userId}:${deviceId}:${nonce}`;
      const exists = await env.CHALLENGES.get(challengeKey);
      if (!exists) return new Response(JSON.stringify({ error: "Invalid or expired challenge" }), { status: 401 });
      await env.CHALLENGES.delete(challengeKey);

      // 2. Fetch stored public key
      const row = await env.DB.prepare(
        "SELECT public_key FROM biometric_keys WHERE user_id = ? AND device_id = ?",
      )
        .bind(userId, deviceId)
        .first<{ public_key: string }>();

      if (!row) return new Response(JSON.stringify({ error: "Device not registered" }), { status: 401 });

      // 3. Verify the signature using Web Crypto
      const publicKeyDer = base64urlDecode(row.public_key);
      const cryptoKey = await crypto.subtle.importKey(
        "spki",
        publicKeyDer,
        { name: "ECDSA", namedCurve: "P-256" },
        false,
        ["verify"],
      );

      const nonceBytes = new TextEncoder().encode(nonce);
      const signatureBytes = base64urlDecode(signature);

      const valid = await crypto.subtle.verify(
        { name: "ECDSA", hash: "SHA-256" },
        cryptoKey,
        signatureBytes,
        nonceBytes,
      );

      if (!valid) return new Response(JSON.stringify({ error: "Signature invalid" }), { status: 401 });

      // 4. Issue a session token (short-lived JWT via Workers, or return a D1-backed session id)
      const sessionToken = crypto.randomUUID();
      // Store session with 8-hour TTL in CHALLENGES namespace (reuse for simplicity)
      await env.CHALLENGES.put(`session:${sessionToken}`, userId, {
        expirationTtl: 60 * 60 * 8,
      });

      return new Response(JSON.stringify({ sessionToken }), {
        headers: { "content-type": "application/json" },
      });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## 3. React Native: Key Generation and Registration

```typescript
// src/auth/biometric.ts
import * as Keychain from "react-native-keychain";
import { Platform } from "react-native";
import { Buffer } from "@craftzdog/react-native-buffer";

const SERVICE = "com.example.app.biometric";

export async function registerBiometricKey(
  userId: string,
  deviceId: string,
  apiBaseUrl: string,
): Promise<void> {
  // react-native-keychain ≥ 8.2 exposes generateKeyPair on iOS/Android
  const keypair = await Keychain.generateKeyPair(SERVICE, {
    accessControl: Keychain.ACCESS_CONTROL.BIOMETRY_CURRENT_SET,
    accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED,
    securityLevel:
      Platform.OS === "android"
        ? Keychain.SECURITY_LEVEL.SECURE_HARDWARE
        : undefined,
  });

  // keypair.publicKey is a base64-encoded DER SubjectPublicKeyInfo
  await fetch(`${apiBaseUrl}/auth/register`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      userId,
      deviceId,
      publicKey: keypair.publicKey,
    }),
  });
}

export async function authenticateWithBiometric(
  userId: string,
  deviceId: string,
  apiBaseUrl: string,
): Promise<string> {
  // 1. Get challenge nonce from Worker
  const challengeRes = await fetch(
    `${apiBaseUrl}/auth/challenge?userId=${userId}&deviceId=${deviceId}`,
  );
  const { nonce } = await challengeRes.json<{ nonce: string }>();

  // 2. Sign the nonce — triggers the biometric prompt
  const signResult = await Keychain.signWithBiometrics(
    SERVICE,
    nonce,
    { promptMessage: "Confirm your identity", cancelButtonText: "Cancel" },
  );

  if (!signResult || typeof signResult !== "string") {
    throw new Error("Biometric authentication failed");
  }

  // signResult is a base64url DER signature
  const verifyRes = await fetch(`${apiBaseUrl}/auth/verify`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ userId, deviceId, nonce, signature: signResult }),
  });

  if (!verifyRes.ok) {
    const err = await verifyRes.json<{ error: string }>();
    throw new Error(err.error);
  }

  const { sessionToken } = await verifyRes.json<{ sessionToken: string }>();
  return sessionToken;
}
```

---

## Anti-Patterns

- **Storing the private key in AsyncStorage or MMKV** — these are plaintext stores. Key generation must go through Keychain/Keystore with hardware-backed storage flags.
- **Signing a static value** — the nonce must be server-issued and single-use. Replay attacks become trivial if the client signs a predictable constant.
- **Using RSA-PSS instead of ECDSA with P-256** — Secure Enclave and StrongBox both support P-256 natively; RSA may fall back to software key generation on older Android devices.
- **Trusting the client-side biometric result** — the device reports success locally; the only trustworthy gate is the server-side signature verification.

---

## Gotchas

- `Keychain.generateKeyPair` and `Keychain.signWithBiometrics` are not in the original `react-native-keychain` stable API. As of v8.2 they are available; verify your installed version exports them before shipping.
- On iOS, keys created with `BIOMETRY_CURRENT_SET` are invalidated when the user adds or removes a fingerprint/face. Handle the `LAErrorBiometryChanged` error by prompting re-registration.
- Cloudflare Workers' `crypto.subtle.importKey` accepts `"spki"` for EC public keys. Ensure the client sends DER-encoded SubjectPublicKeyInfo, not a raw coordinate pair.
- P-256 signatures from the Secure Enclave are in DER format, not the fixed-length `r || s` format that some Web Crypto implementations expect. Pass the raw DER bytes directly.

---

## Verification

1. Register a key pair on a physical device (Secure Enclave / StrongBox does not exist in simulators).
2. Query D1: `SELECT * FROM biometric_keys WHERE user_id = 'test'` to confirm the public key was stored.
3. Run `/auth/challenge` and `/auth/verify` with a correct and an incorrect signature via `curl` to confirm 200 vs 401.
4. Verify single-use nonce: call `/auth/verify` twice with the same nonce — second call must return 401.

---

## Related

- `react-native-biometric-auth.md`
- `biometric-auth.md`
- `react-native-keychain.md`
- `mobile-webauthn-workers-credential-storage.md`
- `capacitor-workers-biometric-webauthn.md`

---

## Sources

- react-native-keychain: https://github.com/oblador/react-native-keychain
- Cloudflare Workers Web Crypto: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- Apple Secure Enclave overview: https://support.apple.com/guide/security/secure-enclave-sec59b0b31ff/web
- Android StrongBox: https://developer.android.com/privacy-and-security/keystore#HardwareSecurityModule
