# jailbreak-root-detection

**Issue:** Jailbreak / root detection for 21+ adult content platforms
**Date:** 2026-08-11
**Status:** documented

## Symptom
A user on a jailbroken iPhone bypasses your in-app age gate because
they patched the local age-verification check with Frida. A rooted
Android user sideloads a modified APK that strips DRM. Apple's App
Store review may also flag missing integrity checks for apps
distributing 18+ content.

## Root cause
**Jailbroken/rooted devices bypass OS-level sandboxing.** App
signatures, entitlement checks, and sandbox restrictions are all
ineffective. For adult content platforms, this is a compliance and
legal risk, not just a security risk — age-verification integrity can
be challenged if the client is trivially bypassable.

**Source:** OWASP MASVS-RESILIENCE:
https://mas.owasp.org/MASVS/controls/MASVS-RESILIENCE-1/

**Source:** Google Play Integrity API (replaces SafetyNet):
https://developer.android.com/google/play/integrity/overview

## Detection layers

Detection works in layers. No single check is foolproof. Layer them
so that bypassing all checks simultaneously is expensive.

```
Layer 1: File system artefacts (fast, bypassable with hide-my-root)
Layer 2: Runtime API checks (SafetyNet / Play Integrity / DeviceCheck)
Layer 3: Behavioural heuristics (su binary call, Frida port scan)
Layer 4: Server-side attestation (Play Integrity verdict from backend)
```

## React Native — `react-native-jail-monkey` (cross-platform)

```bash
npm install jail-monkey
npx pod-install  # iOS
```

```ts
// src/security/integrityCheck.ts
import JailMonkey from 'jail-monkey';

export interface IntegrityResult {
  jailbroken: boolean;
  reasons: string[];
}

export function checkDeviceIntegrity(): IntegrityResult {
  const reasons: string[] = [];

  if (JailMonkey.isJailBroken()) {
    reasons.push('jailbroken_or_rooted');
  }
  if (JailMonkey.canMockLocation()) {
    reasons.push('mock_location_enabled');
  }
  if (JailMonkey.isDebuggedMode()) {
    reasons.push('debugger_attached');
  }
  if (JailMonkey.isDevelopmentSettingsMode?.()) {
    reasons.push('developer_mode');
  }
  // Android only — checks for hooks
  if (JailMonkey.hookDetected?.()) {
    reasons.push('hook_detected');
  }

  return { jailbroken: reasons.length > 0, reasons };
}
```

```ts
// src/screens/AgeGate.tsx
import { checkDeviceIntegrity } from '../security/integrityCheck';

export function AgeGateScreen() {
  useEffect(() => {
    const { jailbroken, reasons } = checkDeviceIntegrity();
    if (jailbroken) {
      // Log to your backend — don't silently ignore
      analytics.track('device_integrity_failed', { reasons });
      // Show a non-dismissible warning; do NOT block outright
      // (Apple rejects apps that refuse to function on jailbroken devices
      // if there's no clear security reason shown to the user)
      setShowIntegrityWarning(true);
    }
  }, []);
}
```

**Apple App Store note:** You MAY warn users and restrict features on
jailbroken devices, but you MUST NOT brick the app entirely unless
you can justify it (financial apps, enterprise MDM). For adult
content, a strong warning + extra server-side verification is the
correct approach.

## iOS — DeviceCheck API (server-side bit setting)

```swift
// ios/App/App/DeviceCheckService.swift
import DeviceCheck

class DeviceCheckService {
  static func generateToken() async throws -> String {
    guard DCDevice.current.isSupported else {
      throw DeviceCheckError.unsupportedDevice
    }
    let tokenData = try await DCDevice.current.generateToken()
    return tokenData.base64EncodedString()
  }
}
```

```ts
// Send token to your Cloudflare Worker for verification
// NativeModules.DeviceCheck.generateToken() from React Native bridge
async function verifyDeviceWithBackend(token: string): Promise<boolean> {
  const response = await apiRequest<{ valid: boolean }>('/auth/device-check', {
    method: 'POST',
    body: JSON.stringify({ deviceToken: token, platform: 'ios' }),
  });
  return response.valid;
}
```

Cloudflare Worker verifies the token with Apple's DeviceCheck API
(`https://api.devicecheck.apple.com/v1/validate_device_token`).

## Android — Play Integrity API (replaces SafetyNet, deprecated 2024)

SafetyNet Attestation API was deprecated in January 2024 and shut
down June 2024. **Use Play Integrity API.**

```bash
# Add to android/app/build.gradle
# implementation 'com.google.android.play:integrity:1.3.0'
```

```kotlin
// android/app/src/main/java/app/example project/PlayIntegrityService.kt
import com.google.android.play.core.integrity.IntegrityManagerFactory
import com.google.android.play.core.integrity.IntegrityTokenRequest
import kotlinx.coroutines.tasks.await

class PlayIntegrityService(private val context: android.content.Context) {

  suspend fun getIntegrityToken(nonce: String): String {
    val integrityManager = IntegrityManagerFactory.create(context)
    val request = IntegrityTokenRequest.builder()
      .setNonce(nonce)         // base64-encoded nonce from your backend
      .setCloudProjectNumber(123456789L)  // from Google Cloud Console
      .build()
    val response = integrityManager.requestIntegrityToken(request).await()
    return response.token()   // encrypted VERDICT_TOKEN
  }
}
```

The token is an encrypted JWT. Send it to your Cloudflare Worker.
Never decode it client-side — only Google's servers can decrypt it.

## Cloudflare Worker — Play Integrity verdict verification

```ts
// workers/src/handlers/playIntegrity.ts
const PLAY_INTEGRITY_URL =
  'https://playintegrity.googleapis.com/v1/tokenPayloadExternal:decode';

interface PlayIntegrityVerdict {
  requestDetails: { requestPackageName: string; nonce: string };
  appIntegrity: { appRecognitionVerdict: string };
  deviceIntegrity: { deviceRecognitionVerdict: string[] };
  accountDetails: { appLicensingVerdict: string };
}

export async function verifyPlayIntegrityToken(
  token: string,
  expectedNonce: string,
  env: Env
): Promise<PlayIntegrityVerdict> {
  const response = await fetch(
    `${PLAY_INTEGRITY_URL}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${env.GOOGLE_ACCESS_TOKEN}`,
      },
      body: JSON.stringify({ integrityToken: token }),
    }
  );

  if (!response.ok) {
    throw new Error(`Play Integrity verification failed: ${response.status}`);
  }

  const verdict = await response.json<PlayIntegrityVerdict>();

  // Validate nonce to prevent replay attacks
  if (verdict.requestDetails.nonce !== expectedNonce) {
    throw new Error('Nonce mismatch — possible replay attack');
  }

  // Validate package name
  if (verdict.requestDetails.requestPackageName !== 'app.example project') {
    throw new Error('Package name mismatch');
  }

  return verdict;
}

// Verdict values to check:
// appIntegrity.appRecognitionVerdict:
//   PLAY_RECOGNIZED — app is genuine
//   UNRECOGNIZED_VERSION — modified or sideloaded
//   UNEVALUATED — not enough data
//
// deviceIntegrity.deviceRecognitionVerdict (array):
//   MEETS_DEVICE_INTEGRITY — passes basic Android checks
//   MEETS_STRONG_INTEGRITY — hardware-backed attestation (Pixel etc.)
//   MEETS_VIRTUAL_INTEGRITY — emulator
//
// accountDetails.appLicensingVerdict:
//   LICENSED — purchased from Play Store
//   UNLICENSED — sideloaded or pirated
```

## Decision matrix

```ts
function evaluateVerdict(verdict: PlayIntegrityVerdict): 'allow' | 'warn' | 'block' {
  const app = verdict.appIntegrity.appRecognitionVerdict;
  const device = verdict.deviceIntegrity.deviceRecognitionVerdict;

  if (app === 'PLAY_RECOGNIZED' && device.includes('MEETS_DEVICE_INTEGRITY')) {
    return 'allow';
  }
  if (app === 'UNEVALUATED') {
    // New install or low traffic — allow with extra monitoring
    return 'warn';
  }
  // Modified APK or rooted without integrity
  return 'block';
}
```

## Verification
- [ ] JailMonkey detects jailbroken iOS device (test on jailbroken device or simulator with tweaks)
- [ ] Play Integrity token is validated server-side
- [ ] Nonce is generated server-side and used only once (stored in KV)
- [ ] SafetyNet references removed from codebase (`grep -r "SafetyNet"`)
- [ ] DeviceCheck token flow tested on physical iOS device (simulator returns unsupported)
- [ ] Warning screen shown to users on non-passing devices

## Gotchas
- **Frida bypass:** `jail-monkey` can be bypassed with a Frida script
  that hooks the file system checks. Server-side Play Integrity is
  the only reliable signal for Android.
- **False positives:** Enterprise MDM, developer mode, and some
  manufacturer customisations can trigger jailbreak checks. Never
  hard-block — always warn + escalate to server-side.
- **SafetyNet is dead.** Any code referencing
  `com.google.android.gms.safetynet` must be replaced.
- **Play Integrity requires a Cloud project** and Google service account.
  Rate limits apply; cache results in KV for 10 minutes with the nonce.
- **iOS Simulator always fails** DeviceCheck. Gate the call on
  `DCDevice.current.isSupported`.
- **Apple guideline 5.6:** Apps that "detect and block" jailbroken
  devices can be rejected if the blocking is the only functionality.
  Always show a warning + allow degraded use, or justify clearly in
  the review notes.

## Related
- `certificate-pinning.md`
- `play-integrity-attestation.md`
- `ios-app-transport-security.md`
- OWASP MASVS-RESILIENCE-1: https://mas.owasp.org/MASVS/controls/MASVS-RESILIENCE-1/
- Google Play Integrity API: https://developer.android.com/google/play/integrity/overview
- Apple DeviceCheck: https://developer.apple.com/documentation/devicecheck
- react-native-jail-monkey: https://github.com/GantMan/jail-monkey
