# Capacitor Biometric Auth Gating Cloudflare Workers API Calls

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Capacitor app must ensure that API calls to a Cloudflare Workers backend are only made after the user has passed biometric authentication, and each request must be cryptographically signed so the Worker can verify it came from a legitimate, authenticated client.

## Context

- Capacitor 6+ (iOS 16 / Android 10+)
- `@aparajita/capacitor-biometric-auth` for biometric prompts
- HMAC signing key stored in iOS Keychain / Android Keystore via `@capacitor/preferences` with secure storage flag
- Workers verify `HMAC-SHA256(key, method + path + timestamp)` with a ±30s clock tolerance
- Fallback to PIN/password when biometrics are unavailable

## HMAC Signing Client (TypeScript)

```typescript
// src/auth/biometricClient.ts
import { BiometricAuth, BiometryError, BiometryErrorType } from '@aparajita/capacitor-biometric-auth';
import { Preferences } from '@capacitor/preferences';

const HMAC_KEY_PREF = 'secure.hmac_key';

// Generate and persist the HMAC key on first run
export async function initHmacKey(): Promise<void> {
  const { value } = await Preferences.get({ key: HMAC_KEY_PREF });
  if (value) return;
  const keyBytes = crypto.getRandomValues(new Uint8Array(32));
  const keyHex = Array.from(keyBytes).map(b => b.toString(16).padStart(2, '0')).join('');
  await Preferences.set({ key: HMAC_KEY_PREF, value: keyHex });
}

async function getHmacKey(): Promise<CryptoKey> {
  const { value } = await Preferences.get({ key: HMAC_KEY_PREF });
  if (!value) throw new Error('HMAC key not initialised');
  const keyBytes = Uint8Array.from(value.match(/.{2}/g)!.map(b => parseInt(b, 16)));
  return crypto.subtle.importKey(
    'raw',
    keyBytes,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
}

async function signRequest(method: string, path: string): Promise<{ signature: string; timestamp: number }> {
  const timestamp = Math.floor(Date.now() / 1000);
  const message = `${method.toUpperCase()}${path}${timestamp}`;
  const key = await getHmacKey();
  const encoder = new TextEncoder();
  const sigBuffer = await crypto.subtle.sign('HMAC', key, encoder.encode(message));
  const signature = btoa(String.fromCharCode(...new Uint8Array(sigBuffer)));
  return { signature, timestamp };
}

export async function authenticatedFetch(
  method: string,
  path: string,
  body?: unknown
): Promise<Response> {
  // 1. Require biometric authentication before proceeding
  try {
    await BiometricAuth.authenticate({
      reason: 'Confirm your identity to continue',
      cancelTitle: 'Cancel',
      allowDeviceCredential: true, // fallback to PIN
    });
  } catch (err) {
    if (
      err instanceof BiometryError &&
      err.code === BiometryErrorType.biometryNotAvailable
    ) {
      // Biometrics not enrolled — fall through to PIN (allowDeviceCredential handles it)
      // If PIN also fails, rethrow
    }
    throw err;
  }

  // 2. Sign the request
  const { signature, timestamp } = await signRequest(method, path);

  // 3. Make the Workers API call
  const res = await fetch(`https://api.example.com${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Signature': signature,
      'X-Timestamp': String(timestamp),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) throw new Error('Signature rejected by server');
  return res;
}
```

## Cloudflare Workers HMAC Verification

```typescript
// worker/src/hmac.ts
interface Env {
  // Per-user HMAC keys are stored in KV keyed by userId
  USER_KEYS: KVNamespace;
}

async function verifyHmac(
  req: Request,
  userId: string,
  env: Env
): Promise<boolean> {
  const signature = req.headers.get('X-Signature');
  const timestampStr = req.headers.get('X-Timestamp');
  if (!signature || !timestampStr) return false;

  const timestamp = parseInt(timestampStr, 10);
  const now = Math.floor(Date.now() / 1000);
  // Reject requests outside ±30s window
  if (Math.abs(now - timestamp) > 30) return false;

  const keyHex = await env.USER_KEYS.get(userId);
  if (!keyHex) return false;

  const keyBytes = Uint8Array.from(
    keyHex.match(/.{2}/g)!.map((b: string) => parseInt(b, 16))
  );
  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    keyBytes,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify']
  );

  const url = new URL(req.url);
  const message = `${req.method}${url.pathname}${timestamp}`;
  const encoder = new TextEncoder();
  const sigBytes = Uint8Array.from(atob(signature), c => c.charCodeAt(0));

  return crypto.subtle.verify('HMAC', cryptoKey, sigBytes, encoder.encode(message));
}

export async function handleProtected(
  req: Request,
  env: Env
): Promise<Response> {
  // userId extracted from a JWT or session cookie (not shown)
  const userId = req.headers.get('X-User-Id') ?? '';
  const valid = await verifyHmac(req, userId, env);
  if (!valid) return new Response('Unauthorized', { status: 401 });

  // Proceed with the actual handler
  return Response.json({ ok: true });
}
```

## Key Registration Flow

```typescript
// During account setup (after login, before first authenticated request)
export async function registerHmacKeyWithServer(userId: string): Promise<void> {
  await initHmacKey();
  const { value: keyHex } = await Preferences.get({ key: HMAC_KEY_PREF });

  // Upload the public key to the Worker KV over a normal auth-token-secured channel
  await fetch('https://api.example.com/keys/register', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${await getSessionToken()}`,
    },
    body: JSON.stringify({ userId, hmacKey: keyHex }),
  });
}

async function getSessionToken(): Promise<string> {
  // Retrieve a conventional JWT from Preferences or memory
  const { value } = await Preferences.get({ key: 'session.token' });
  return value ?? '';
}
```

## Anti-patterns

- **Storing the HMAC key in plain `localStorage`** — it is readable by any JavaScript on the page; use `@capacitor/preferences` which maps to Keychain/Keystore on native.
- **Not enforcing a timestamp window** — without a ±30s check, captured requests can be replayed indefinitely.
- **Signing only the path without the method** — a signed GET request could be replayed as a DELETE if method is excluded from the signing string.
- **Re-prompting biometrics on every HTTP call** — gate at the feature level (e.g., opening a screen), not per-request; cache the biometric result for the session.
- **Sharing one HMAC key across devices** — each device should generate and register its own key so individual devices can be revoked.

## Gotchas

- Android's `AndroidKeyStore` backed by hardware is only available on devices with a Trusted Execution Environment; `@capacitor/preferences` on Android uses `EncryptedSharedPreferences` which provides software-backed encryption on older devices.
- `crypto.subtle` is unavailable in some older Capacitor WebViews; verify with `typeof crypto.subtle !== 'undefined'` and fall back to a JS HMAC library.
- iOS Keychain items created without `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` are backed up to iCloud; ensure the HMAC key is device-bound.
- Workers `crypto.subtle.verify` is available in the Workers runtime without importing anything — no polyfill needed.

## Verification

1. Call `authenticatedFetch('GET', '/api/items')` — a biometric prompt should appear before the network request fires.
2. Capture the request in a proxy; replay it after 31 seconds — the Worker should return 401.
3. Tamper with the `X-Signature` header — Worker should return 401.
4. Remove biometric enrollment from the device — verify the app falls back to PIN without crashing.
5. In KV, delete the user's key entry; subsequent requests should return 401.

## Related

- `documentation/workers/kv-per-user-secrets.md`
- `documentation/docs/policies/mobile/capacitor-secure-storage.md`
- `documentation/workers/request-signing.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/kv/
- https://github.com/aparajita/capacitor-biometric-auth
- https://capacitorjs.com/docs/apis/preferences
