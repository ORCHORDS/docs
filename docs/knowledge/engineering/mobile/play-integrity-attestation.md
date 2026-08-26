# play-integrity-attestation

**Issue:** Google Play Integrity API replacing SafetyNet — VERDICT_TOKEN, Cloudflare Worker verification
**Date:** 2026-08-11
**Status:** documented

## Symptom
You call `SafetyNet.attest()` and get
`SafetyNetApi has been deprecated` in the logs. Or your backend
receives no attestation for new Android 14 installs. Google shut
down SafetyNet Attestation in **January 2025** (the final deadline
after multiple extensions). All attestation must now use the
**Play Integrity API**.

## Root cause
**SafetyNet is dead.** Google deprecated it in 2022 and shut the
API down entirely in January 2025. Any app still calling
`com.google.android.gms.safetynet.SafetyNetApi` receives a
`CANCELED` or silent failure.

The Play Integrity API provides three checks in one call:
1. **App integrity** — is this a genuine, Play-distributed build?
2. **Device integrity** — does the device pass Android hardware integrity?
3. **Account integrity** — was the app licensed from the Play Store?

**Source:** Google Play Integrity API overview:
https://developer.android.com/google/play/integrity/overview

**Source:** SafetyNet sunset announcement:
https://developer.android.com/training/safetynet/deprecation-timeline

## Architecture overview

```
Android App                    Cloudflare Worker            Google Play Integrity API
    |                               |                               |
    |-- 1. GET /integrity/nonce --> |                               |
    |<- nonce (stored in KV) ------ |                               |
    |                               |                               |
    |-- 2. requestIntegrityToken(nonce) --------------------------> |
    |<- VERDICT_TOKEN (encrypted) --------------------------------- |
    |                               |                               |
    |-- 3. POST /integrity/verify   |                               |
    |       { token, nonce } -----> |                               |
    |                         decode token -----------------------> |
    |                               | <-- PlayIntegrityVerdict ---- |
    |                               |                               |
    |<-- { verdict, sessionToken } -|                               |
```

## Step 1 — Cloudflare Worker: issue a nonce

```ts
// workers/src/handlers/integrity.ts

export async function issueNonce(env: Env): Promise<Response> {
  // Nonce must be base64-encoded, URL-safe, ≥ 16 bytes
  const raw = crypto.getRandomValues(new Uint8Array(32));
  const nonce = btoa(String.fromCharCode(...raw))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');

  // Store nonce in KV — single use, 5 minute TTL
  await env.KV.put(`integrity:nonce:${nonce}`, '1', { expirationTtl: 300 });

  return Response.json({ nonce });
}
```

## Step 2 — Android: request the integrity token

```kotlin
// android/app/src/main/java/app/example project/PlayIntegrityClient.kt
import com.google.android.play.core.integrity.IntegrityManagerFactory
import com.google.android.play.core.integrity.IntegrityTokenRequest
import kotlinx.coroutines.tasks.await

class PlayIntegrityClient(private val context: android.content.Context) {

  // Cloud project number from Google Cloud Console
  // (NOT the Play Console project number — the GCP project linked to Play)
  private val cloudProjectNumber = 123456789L

  suspend fun getToken(nonce: String): String {
    val manager = IntegrityManagerFactory.create(context)
    val request = IntegrityTokenRequest.builder()
      .setNonce(nonce)
      .setCloudProjectNumber(cloudProjectNumber)
      .build()
    val response = manager.requestIntegrityToken(request).await()
    return response.token()
  }
}
```

```ts
// src/api/integrityFlow.ts (React Native / Capacitor JS layer)

// If using a Capacitor native plugin bridge:
declare const NativeIntegrity: {
  getToken: (nonce: string) => Promise<{ token: string }>;
};

export async function performIntegrityCheck(): Promise<string | null> {
  try {
    // Step 1: get nonce from our backend
    const { nonce } = await apiRequest<{ nonce: string }>('/integrity/nonce');

    // Step 2: get Play Integrity token (calls native Kotlin code)
    const { token } = await NativeIntegrity.getToken(nonce);

    // Step 3: verify with our backend
    const { sessionToken } = await apiRequest<{ sessionToken: string }>(
      '/integrity/verify',
      {
        method: 'POST',
        body: JSON.stringify({ token, nonce }),
      }
    );

    return sessionToken;
  } catch (error) {
    console.error('[Integrity] Check failed:', error);
    return null;  // Degrade gracefully; do not block all users
  }
}
```

## Step 3 — Cloudflare Worker: verify the token

The `VERDICT_TOKEN` is an encrypted JWT. You must decode it using
the Play Integrity API server endpoint. The token is **not** a
standard JWT you can decode locally — it is encrypted with
Google's server key.

```ts
// workers/src/handlers/integrityVerify.ts

const PLAY_INTEGRITY_DECODE_URL =
  'https://playintegrity.googleapis.com/v1/{packageName}:decodeIntegrityToken';

export interface PlayIntegrityVerdict {
  tokenPayloadExternal: {
    requestDetails: {
      requestPackageName: string;
      timestampMillis: string;
      nonce: string;
    };
    appIntegrity: {
      appRecognitionVerdict: 'PLAY_RECOGNIZED' | 'UNRECOGNIZED_VERSION' | 'UNEVALUATED';
      packageName: string;
      certificateSha256Digest: string[];
      versionCode: string;
    };
    deviceIntegrity: {
      deviceRecognitionVerdict: Array<
        | 'MEETS_DEVICE_INTEGRITY'
        | 'MEETS_BASIC_INTEGRITY'
        | 'MEETS_STRONG_INTEGRITY'
        | 'MEETS_VIRTUAL_INTEGRITY'
      >;
    };
    accountDetails: {
      appLicensingVerdict: 'LICENSED' | 'UNLICENSED' | 'UNEVALUATED';
    };
  };
}

export async function verifyIntegrityToken(
  token: string,
  nonce: string,
  env: Env
): Promise<PlayIntegrityVerdict['tokenPayloadExternal']> {
  // Verify nonce is fresh (single-use)
  const nonceKey = `integrity:nonce:${nonce}`;
  const storedNonce = await env.KV.get(nonceKey);
  if (!storedNonce) {
    throw new Error('Nonce not found or expired — possible replay attack');
  }
  // Consume nonce immediately (single use)
  await env.KV.delete(nonceKey);

  // Call Google Play Integrity API
  const url = PLAY_INTEGRITY_DECODE_URL.replace('{packageName}', 'app.example project');
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${env.GOOGLE_PLAY_INTEGRITY_ACCESS_TOKEN}`,
    },
    body: JSON.stringify({ integrityToken: token }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Play Integrity API error ${response.status}: ${text}`);
  }

  const verdict = await response.json<PlayIntegrityVerdict>();
  const payload = verdict.tokenPayloadExternal;

  // Validate nonce matches
  if (payload.requestDetails.nonce !== nonce) {
    throw new Error('Nonce mismatch in verdict');
  }

  // Validate package name
  if (payload.requestDetails.requestPackageName !== 'app.example project') {
    throw new Error('Package name mismatch');
  }

  // Validate token age (tokens are valid for 1 hour)
  const issued = parseInt(payload.requestDetails.timestampMillis);
  if (Date.now() - issued > 60 * 60 * 1000) {
    throw new Error('Token too old');
  }

  return payload;
}
```

## Verdict evaluation — what to do with each verdict

```ts
// workers/src/handlers/integrityEvaluate.ts

type IntegrityDecision = 'allow' | 'challenge' | 'block';

interface EvaluationResult {
  decision: IntegrityDecision;
  reason?: string;
}

export function evaluateVerdict(
  payload: PlayIntegrityVerdict['tokenPayloadExternal']
): EvaluationResult {
  const app = payload.appIntegrity.appRecognitionVerdict;
  const device = payload.deviceIntegrity.deviceRecognitionVerdict;
  const license = payload.accountDetails.appLicensingVerdict;

  // Modified APK or sideloaded
  if (app === 'UNRECOGNIZED_VERSION') {
    return { decision: 'block', reason: 'modified_apk' };
  }

  // Device does not pass basic Android integrity
  if (!device.includes('MEETS_BASIC_INTEGRITY') &&
      !device.includes('MEETS_DEVICE_INTEGRITY')) {
    return { decision: 'challenge', reason: 'device_integrity_failed' };
  }

  // Not purchased from Play Store (sideloaded or pirated)
  if (license === 'UNLICENSED') {
    return { decision: 'challenge', reason: 'unlicensed' };
  }

  // UNEVALUATED — new install, insufficient signal
  if (app === 'UNEVALUATED' || license === 'UNEVALUATED') {
    return { decision: 'challenge', reason: 'unevaluated' };
  }

  return { decision: 'allow' };
}
```

## Setting up the Google service account

1. Create a Google Cloud Project (or use existing one linked to Play)
2. Enable the **Google Play Integrity API** in the GCP console
3. Create a service account with the **Service Account Token Creator**
   role
4. Download the service account JSON key
5. In your Cloudflare Worker, exchange the service account credentials
   for a short-lived access token (OAuth 2.0 JWT grant):

```ts
// workers/src/lib/googleAuth.ts

export async function getGoogleAccessToken(
  serviceAccountJson: string
): Promise<string> {
  const sa = JSON.parse(serviceAccountJson);
  const now = Math.floor(Date.now() / 1000);

  const header = { alg: 'RS256', typ: 'JWT' };
  const claim = {
    iss: sa.client_email,
    scope: 'https://www.googleapis.com/auth/playintegrity',
    aud: 'https://oauth2.googleapis.com/token',
    exp: now + 3600,
    iat: now,
  };

  // Sign the JWT with the service account private key using Web Crypto
  const encoder = new TextEncoder();
  const headerB64 = btoa(JSON.stringify(header)).replace(/=/g, '');
  const claimB64 = btoa(JSON.stringify(claim)).replace(/=/g, '');
  const signingInput = `${headerB64}.${claimB64}`;

  const keyData = sa.private_key
    .replace('<redacted-private-key>', '')
    .replace(/\n/g, '');

  const cryptoKey = await crypto.subtle.importKey(
    'pkcs8',
    Uint8Array.from(atob(keyData), c => c.charCodeAt(0)),
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const signature = await crypto.subtle.sign(
    'RSASSA-PKCS1-v1_5',
    cryptoKey,
    encoder.encode(signingInput)
  );

  const signatureB64 = btoa(String.fromCharCode(...new Uint8Array(signature)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');

  const jwt = `${signingInput}.${signatureB64}`;

  const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion: jwt,
    }),
  });

  const { access_token } = await tokenResponse.json<{ access_token: string }>();
  return access_token;
}
```

Cache the access token in KV for 55 minutes (it expires in 60).

## Play Console setup

1. In Google Play Console → Setup → API access → link to the GCP project
2. Grant the service account "View app information" on your app
3. Verify the Cloud Project Number matches your app in Play Console
   (Play Console → Monetize → Play Integrity API)

## Verification
- [ ] `grep -r "SafetyNet" android/` — no references
- [ ] `grep -r "safetynet" android/` — no references
- [ ] Nonce is consumed (deleted from KV) after use
- [ ] Token age is validated (< 1 hour)
- [ ] Package name is validated in verdict
- [ ] Service account key is stored in Worker Secrets, not `wrangler.toml`
- [ ] `GOOGLE_PLAY_INTEGRITY_ACCESS_TOKEN` is cached in KV with 55-minute TTL
- [ ] Test with emulator: verdict should show `MEETS_VIRTUAL_INTEGRITY`
- [ ] Test with physical Pixel: verdict shows `MEETS_STRONG_INTEGRITY`

## Gotchas
- **`cloudProjectNumber` is not the Play Console app ID**. It is the
  Google Cloud Project number (12-digit integer from GCP Console →
  Project Info → Project number).
- **Tokens are rate-limited**: 10,000 requests/day for standard access;
  request higher quota via Play Console for production use.
- **Emulators always return `MEETS_VIRTUAL_INTEGRITY`** — they never
  pass `MEETS_DEVICE_INTEGRITY`. Test on physical hardware for full
  verdict data.
- **`UNEVALUATED` is not a failure** for a brand-new app install
  with low signal. Treat it as `challenge` (require extra verification),
  not `block`.
- **Replay attacks**: the nonce must be single-use and verified
  server-side. If you skip nonce validation, an attacker can capture
  a passing verdict and replay it.
- **Token TTL**: tokens are valid for 1 hour from issuance, but Google
  recommends only accepting them for ~10 minutes in high-security flows
  (payment, age verification).
- **The `integrityToken` is NOT a JWT you can decode locally.** It is
  encrypted with a Google key. Any code that tries `jwt.decode(token)`
  will get garbage. Always use the server-side decode endpoint.

## Related
- `jailbreak-root-detection.md`
- `certificate-pinning.md`
- `android-network-security-config.md`
- Google Play Integrity API: https://developer.android.com/google/play/integrity/overview
- Play Integrity API reference: https://developer.android.com/google/play/integrity/reference
- SafetyNet deprecation timeline: https://developer.android.com/training/safetynet/deprecation-timeline
- GCP service account auth: https://developers.google.com/identity/protocols/oauth2/service-account
