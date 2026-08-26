# cross-platform-app-attestation-device-integrity

**Issue:** Verifying on the backend that a request genuinely came from your mobile app on a non-tampered device, across iOS and Android
**Date:** 2026-08-12
**Status:** documented

## Symptom / Context
Your API is being abused: scraped by modified clients, replayed by bots, or hit from an
emulator farm. You need the server to reject any request that isn't backed by a genuine
device running an unmodified build of your app. On iOS this is DeviceCheck / App Attest;
on Android it's Play Integrity. You need a single backend verifier that handles both.

## Pattern / Solution

**Client side — request a fresh assertion per sensitive call:**

iOS (Swift, via Capacitor/RN bridge or native):
```swift
let service = DCAppAttestService.shared!
// 1. One-time: generate + attest a key, send attestation to backend bound to user
service.generateKey { keyId, _ in /* persist keyId */ }
service.attestKey(keyId, clientDataHash: hash(body + nonce)) { attestation, _ in /* -> backend */ }
// 2. Per sensitive request: generate an assertion over the request body + server nonce
service.generateAssertion(keyId, clientDataHash: hash(body + nonce)) { assertion, _ in
    // attach assertion as the X-Attestation-Token header
}
```

Android (Kotlin):
```kotlin
val tokenProvider = StandardIntegrityTokenProvider(androidKeySet) // or Play provider
val request = IntegrityTokenRequest.builder()
    .setNonce(serverNonceBase64)            // server-issued, single-use
    .setCloudProjectNumber(cloudProjectNumber)
    .build()
tokenProvider.requestIntegrityToken(request).addOnSuccessListener { response ->
    val token = response.token()           // send to backend
}
```

**Backend side — single verifier middleware:**
```ts
// Pseudocode — one entry point for both platforms
async function verifyAttestation(req: Request): Promise<{ ok: boolean; deviceId?: string }> {
  const platform = req.headers['x-app-platform']; // 'ios' | 'android'
  const token = req.headers['x-attestation-token'];

  if (platform === 'ios') {
    // Apple App Attest: verify assertion against the stored public key for this keyId
    const ok = await verifyAppAttestAssertion({
      keyId: req.user.keyId,
      clientDataHash: hash(req.body + req.nonce),
      assertion: token,
      environment: process.env.NODE_ENV, // development | production
    });
    return { ok, deviceId: req.user.keyId };
  }
  if (platform === 'android') {
    const verdict = await playIntegrity.verify({ token, requestHash: hash(req.body + req.nonce) });
    return {
      ok: verdict.deviceRecognitionVerdict === 'MEETS_DEVICE_INTEGRITY' && verdict.appIntegrity === 'PLAY_RECOGNIZED',
      deviceId: verdict.deviceIdentifier,
    };
  }
  return { ok: false };
}
```

**Server-issued nonce is mandatory:** every attestation call must be bound to a server
nonce and a hash of the request body. Without it, a captured token is replayable.

## Gotchas
- App Attest and Play Integrity both have rate limits. Re-attesting on every API call will
  exhaust your quota within minutes on a real user base. Attest once, assert per call, and
  only assert on high-value endpoints (payments, account creation, scraping-prone reads).
- The iOS assertion is bound to the **clientDataHash you compute**. Mismatched hash
  algorithms (SHA-256 on client, something else on server) produce silent failures — verify
  byte-for-byte, including nonce concatenation order.
- Play Integrity's `requestHash` field is the SHA-256 of (nonce + body). Truncating the body
  before hashing (a common "optimization") causes the verdict to return `MEETS_VERICT` but
  with `requestHashMismatch`. Always hash the full body.
- `MEETS_BASIC_INTEGRITY` (Android) includes emulators and unlocked bootloaders. Use
  `MEETS_DEVICE_INTEGRITY` or stricter `MEETS_STRONG_INTEGRITY` for sensitive flows.
- iOS App Attest in development uses a different root than production. Your verifier must
  accept both during testing or your dev build will look "tampered."
- Keys are per-device, not per-user — store keyId-to-device, not keyId-to-user, or you'll
  revoke the wrong device on logout.
- Play Integrity response decryption requires Google's public PEM pinned server-side;
  rotating your backend without re-pinning silently breaks verification.
- The 2026 App Store Accountability age signals ride on the same attestation envelope. If
  you're already verifying attestation, extend the verifier to read the age-band claim
  rather than building a parallel flow (see `mobile-age-verification-compliance-2026.md`).
- WebView-only apps (Capacitor, Cordova) cannot call App Attest directly from JS — bridge to native.

## Related
- `play-integrity-attestation.md`
- `mobile-age-verification-compliance-2026.md`
- `mobile-auth-oauth-pkce.md`
- `certificate-pinning.md`
- `jailbreak-root-detection.md`
