# certificate-pinning

**Issue:** TLS certificate pinning in React Native / Capacitor — OWASP MASVS-NETWORK
**Date:** 2026-08-11
**Status:** documented

## Symptom
Your Capacitor app passes all store checks but traffic is intercepted
by a MITM proxy (Burp Suite, mitmproxy) on a rooted device. A
researcher files a vulnerability report. Your adult-content API calls
— including age-verification tokens and payment details — are fully
readable. The certificate is valid; pinning was never implemented.

## Root cause
**TLS verifies the CA chain, not the specific server certificate.**
Without pinning, any certificate signed by a trusted CA (including
corporate MitM proxies and rogue CAs installed on the device) is
accepted.

**Source:** OWASP MASVS-NETWORK:
https://mas.owasp.org/MASVS/controls/MASVS-NETWORK-2/

**Source:** OWASP MSTG — Testing Custom Certificate Stores:
https://mas.owasp.org/MASTG/tests/android/MASVS-NETWORK/MASTG-TEST-0021/

## Why it matters for example.com

example.com is an adult content platform. Certificate pinning is not
required by Apple or Google, but failing to pin:
- Exposes age-verification JWT tokens to interception
- Exposes Creator payout API calls
- Increases risk of credential theft on shared/public Wi-Fi
- Can be cited in a security audit as a critical finding

MASVS-NETWORK-2 is **L2** (defence-in-depth), not L1 (baseline).
Implement it before the first production release.

## The "certificate pinning" approaches

| Approach | Pros | Cons |
|---|---|---|
| Public key pinning (SPKI) | Survives cert renewal | Must pin new key before rotation |
| Certificate hash pinning | Simple | Must update on every renewal |
| CA pinning | Easy rotation | Weaker; pins intermediate CA |

**Recommended:** SPKI (Subject Public Key Info) hash pinning with a
backup pin. This is what RFC 7469 (HPKP) and modern libraries use.

## Generating SPKI hashes

```bash
# From the live server
openssl s_client -connect api.example.com:443 -servername api.example.com \
  </dev/null 2>/dev/null \
  | openssl x509 -pubkey -noout \
  | openssl pkey -pubin -outform der \
  | openssl dgst -sha256 -binary \
  | openssl enc -base64

# From a PEM file
openssl x509 -in cert.pem -pubkey -noout \
  | openssl pkey -pubin -outform der \
  | openssl dgst -sha256 -binary \
  | openssl enc -base64
```

Run this for both the current cert and the backup cert (next rotation).

## React Native — using `react-native-ssl-pinning`

```bash
npm install react-native-ssl-pinning
npx pod-install   # iOS
```

```ts
// src/api/client.ts
import { fetch } from 'react-native-ssl-pinning';

const API_BASE = 'https://api.example.com';

// SPKI SHA-256 hashes — current cert + one backup
const PINS = [
  'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=',  // current
  'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',  // backup — rotate BEFORE current expires
];

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    },
    body: options.body as string,
    sslPinning: {
      certs: PINS,
    },
    timeoutInterval: 10000,
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}
```

## Capacitor (iOS + Android) — native plugin approach

For Capacitor apps, the WebView uses the system network stack. You
must pin at the **native layer**, not in JavaScript.

### iOS — `AppDelegate.swift` with URLSession pinning

```swift
// ios/App/App/AppDelegate.swift
import UIKit
import Capacitor

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {

  var window: UIWindow?

  func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return true
  }
}

// ios/App/App/PinnedURLSession.swift
import Foundation
import CommonCrypto

/// SPKI SHA-256 hashes for api.example.com — update before cert rotation
private let pinnedHashes: Set<String> = [
  "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=",  // current
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",  // backup
]

class PinningDelegate: NSObject, URLSessionDelegate {
  func urlSession(
    _ session: URLSession,
    didReceive challenge: URLAuthenticationChallenge,
    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
  ) {
    guard
      challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
      let serverTrust = challenge.protectionSpace.serverTrust,
      SecTrustEvaluateWithError(serverTrust, nil)
    else {
      completionHandler(.cancelAuthenticationChallenge, nil)
      return
    }

    // Get the leaf certificate's public key
    guard
      let certificate = SecTrustGetCertificateAtIndex(serverTrust, 0),
      let publicKey = SecCertificateCopyKey(certificate),
      let publicKeyData = SecKeyCopyExternalRepresentation(publicKey, nil) as Data?
    else {
      completionHandler(.cancelAuthenticationChallenge, nil)
      return
    }

    // Compute SPKI hash
    let hash = sha256WithHeader(publicKeyData)
    let base64 = hash.base64EncodedString()

    if pinnedHashes.contains(base64) {
      completionHandler(.useCredential, URLCredential(trust: serverTrust))
    } else {
      completionHandler(.cancelAuthenticationChallenge, nil)
    }
  }

  // RSA-2048 SPKI header — adjust if you use EC keys
  private let rsa2048Header = Data([
    0x30, 0x82, 0x01, 0x22, 0x30, 0x0d, 0x06, 0x09,
    0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01,
    0x01, 0x05, 0x00, 0x03, 0x82, 0x01, 0x0f, 0x00,
  ])

  private func sha256WithHeader(_ publicKey: Data) -> Data {
    var keyWithHeader = rsa2048Header
    keyWithHeader.append(publicKey)
    var hash = UInt8)
    keyWithHeader.withUnsafeBytes {
      _ = CC_SHA256($0.baseAddress, CC_LONG(keyWithHeader.count), &hash)
    }
    return Data(hash)
  }
}
```

### Android — `network_security_config.xml`

See `android-network-security-config.md` for the full XML approach.
For dynamic pinning in Capacitor:

```kotlin
// android/app/src/main/java/app/example project/MainActivity.kt
import android.os.Bundle
import com.getcapacitor.BridgeActivity
import okhttp3.CertificatePinner
import okhttp3.OkHttpClient

class MainActivity : BridgeActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
  }
}
```

For OkHttp-based requests outside the WebView:

```kotlin
val pinner = CertificatePinner.Builder()
  .add("api.example.com", "sha256/BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=")
  .add("api.example.com", "sha256/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
  .build()

val client = OkHttpClient.Builder()
  .certificatePinner(pinner)
  .build()
```

## Certificate rotation procedure

1. Generate new key pair at least 30 days before cert expiry
2. Compute SPKI hash of new cert: see "Generating SPKI hashes" above
3. Add new hash as backup pin in the **current** app release (ship it)
4. Wait for app update to propagate (≥ 2 weeks)
5. Rotate the cert on the server
6. In the next app release, remove the old hash, make new hash primary

**Never** remove the old pin before the new cert is live. **Never**
release an app with only one pin — if the cert expires and you can't
ship fast enough, you lock out all users.

## Bypass risks

- **Frida hooks** on rooted devices can bypass URLSession delegates
- **`trustkit`** and similar libraries can be patched
- Pinning + jailbreak/root detection is the correct combo; neither alone is sufficient
- Always pair with `jailbreak-root-detection.md`

## Verification
- [ ] `mitmproxy` on the same Wi-Fi as a test device: requests fail
- [ ] Legitimate API calls succeed with the pinned cert
- [ ] Backup pin hash is computed and committed before release
- [ ] Cert expiry alert is set (PagerDuty / Cloudflare) at -60 days
- [ ] Rotation runbook is documented in `RUNBOOK.md`

## Gotchas
- **WebView traffic is NOT pinned** by URLSession delegates. The
  Capacitor WebView uses `WKWebView` which ignores `URLSessionDelegate`.
  Pinning in the WKWebView layer requires a `WKURLSchemeHandler` or
  a native Capacitor plugin that intercepts requests.
- **OkHttp vs WebView:** Android's WebView also ignores OkHttp's
  `CertificatePinner`. Pin at the `network_security_config.xml` level
  for WebView traffic (Android only).
- **Let's Encrypt 90-day certs** make rotation critical. Set a
  calendar reminder 60 days out.
- **CDN / Cloudflare:** If you terminate TLS at Cloudflare, pin
  Cloudflare's intermediate CA key, not your origin cert.

## Related
- `jailbreak-root-detection.md`
- `android-network-security-config.md`
- `ios-app-transport-security.md`
- OWASP MASVS-NETWORK-2: https://mas.owasp.org/MASVS/controls/MASVS-NETWORK-2/
- OWASP MSTG Android: https://mas.owasp.org/MASTG/tests/android/MASVS-NETWORK/MASTG-TEST-0021/
- OWASP MSTG iOS: https://mas.owasp.org/MASTG/tests/ios/MASVS-NETWORK/MASTG-TEST-0066/
- RFC 7469 (HPKP): https://datatracker.ietf.org/doc/html/rfc7469
