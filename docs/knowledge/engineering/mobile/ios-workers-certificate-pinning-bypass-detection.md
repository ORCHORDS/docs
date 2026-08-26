# iOS Workers Certificate Pinning Bypass Detection

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

On jailbroken devices, tools such as Frida, SSL Kill Switch 2, and objection can intercept HTTPS traffic even when the app pins certificates. The app cannot fully prevent this (an attacker controls the OS), but it can detect the conditions, report the anomaly to Workers, and gracefully degrade — refusing sensitive operations rather than silently leaking data.

## Context

There are two complementary layers:

1. **Client-side heuristics** — detect the pinning bypass at runtime in Swift (hook presence, dylib injection, `/etc/hosts` tampering).
2. **Server-side verification** — Workers validates a signed attestation from Apple App Attest; if the device attestation is absent or stale, Workers refuses token issuance.

This article focuses on the detection + reporting flow to Workers. For App Attest setup, see `apple-app-attest-retry-and-risk-metric-preservation.md`.

---

## URLSession Delegate: Certificate Pinning

```swift
// Sources/Network/PinningURLSessionDelegate.swift
import Foundation
import CryptoKit

final class PinningURLSessionDelegate: NSObject, URLSessionDelegate {

  // SHA-256 of the DER-encoded SubjectPublicKeyInfo — update on cert rotation
  private static let pinnedHashes: Set<String> = [
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",  // primary leaf
    "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=",  // backup leaf
  ]

  func urlSession(
    _ session: URLSession,
    didReceive challenge: URLAuthenticationChallenge,
    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
  ) {
    guard
      challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
      let serverTrust = challenge.protectionSpace.serverTrust
    else {
      completionHandler(.cancelAuthenticationChallenge, nil)
      return
    }

    // Evaluate against system roots first
    var error: CFError?
    guard SecTrustEvaluateWithError(serverTrust, &error) else {
      PinningBypassReporter.shared.report(.chainEvaluationFailed)
      completionHandler(.cancelAuthenticationChallenge, nil)
      return
    }

    // Extract leaf SPKI hash
    guard
      let cert = SecTrustGetCertificateAtIndex(serverTrust, 0),
      let spkiHash = spkiHash(of: cert)
    else {
      completionHandler(.cancelAuthenticationChallenge, nil)
      return
    }

    if Self.pinnedHashes.contains(spkiHash) {
      completionHandler(.useCredential, URLCredential(trust: serverTrust))
    } else {
      // Hash mismatch — potential MITM or bypass
      PinningBypassReporter.shared.report(.hashMismatch(observed: spkiHash))
      completionHandler(.cancelAuthenticationChallenge, nil)
    }
  }

  private func spkiHash(of cert: SecCertificate) -> String? {
    guard let data = SecCertificateCopyKey(cert).flatMap({ SecKeyCopyExternalRepresentation($0, nil) as Data? }) else {
      return nil
    }
    let digest = SHA256.hash(data: data)
    return Data(digest).base64EncodedString()
  }
}
```

## Runtime Bypass Heuristics

```swift
// Sources/Security/BypassDetector.swift
import Foundation
import MachO

struct BypassDetector {

  static func run() -> [BypassSignal] {
    var signals: [BypassSignal] = []

    // 1. SSL Kill Switch 2 dylib
    if isDylibLoaded(matching: "SSLKillSwitch") {
      signals.append(.sslKillSwitchDylib)
    }

    // 2. Frida gadget
    if isDylibLoaded(matching: "FridaGadget") || isDylibLoaded(matching: "frida-agent") {
      signals.append(.fridaGadget)
    }

    // 3. Suspicious dylib count spike (> 400 loaded images is unusual)
    if _dyld_image_count() > 400 {
      signals.append(.excessiveDylibCount(count: Int(_dyld_image_count())))
    }

    // 4. /etc/hosts modified (common proxy redirect)
    if hostsFileModified() {
      signals.append(.hostsFileTampered)
    }

    // 5. Jailbreak paths (belt-and-suspenders with App Attest)
    let jailbreakPaths = ["/usr/bin/cycript", "/bin/bash", "/usr/sbin/sshd", "/etc/apt"]
    for path in jailbreakPaths where FileManager.default.fileExists(atPath: path) {
      signals.append(.jailbreakPath(path: path))
    }

    return signals
  }

  private static func isDylibLoaded(matching name: String) -> Bool {
    let count = _dyld_image_count()
    for i in 0..<count {
      if let imgName = _dyld_get_image_name(i), String(cString: imgName).contains(name) {
        return true
      }
    }
    return false
  }

  private static func hostsFileModified() -> Bool {
    guard let attrs = try? FileManager.default.attributesOfItem(atPath: "/etc/hosts"),
          let modDate = attrs[.modificationDate] as? Date else { return false }
    // Flag if /etc/hosts was touched in the last 24 h — heuristic only
    return Date().timeIntervalSince(modDate) < 86400
  }
}

enum BypassSignal: Codable {
  case sslKillSwitchDylib
  case fridaGadget
  case excessiveDylibCount(count: Int)
  case hostsFileTampered
  case jailbreakPath(path: String)
  case chainEvaluationFailed
  case hashMismatch(observed: String)
}
```

## Report to Workers

```swift
// Sources/Security/PinningBypassReporter.swift
import Foundation

final class PinningBypassReporter {
  static let shared = PinningBypassReporter()

  private let workersURL = URL(string: "https://api.example.com/security/pinning-event")!

  func report(_ signal: BypassSignal) {
    Task.detached(priority: .utility) {
      let payload = PinningEventPayload(
        signal: signal,
        bundle_id: Bundle.main.bundleIdentifier ?? "",
        app_version: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "",
        timestamp: ISO8601DateFormatter().string(from: Date())
      )

      guard let body = try? JSONEncoder().encode(payload) else { return }

      // Use a plain URLSession without pinning to ensure the report reaches Workers
      // even if the pinned session is the one being bypassed
      var request = URLRequest(url: self.workersURL)
      request.httpMethod = "POST"
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
      request.httpBody = body

      _ = try? await URLSession.shared.data(for: request)
    }
  }
}

struct PinningEventPayload: Codable {
  let signal: BypassSignal
  let bundle_id: String
  let app_version: String
  let timestamp: String
}
```

## Workers: Pinning Event Receiver

```typescript
// workers/src/security/pinningEvent.ts
import { Env } from '../types';

interface PinningEvent {
  signal: Record<string, unknown>;
  bundle_id: string;
  app_version: string;
  timestamp: string;
}

export async function handlePinningEvent(
  request: Request,
  env: Env
): Promise<Response> {
  const event = await request.json<PinningEvent>();

  const cf = request.cf ?? {};

  await env.ANALYTICS.writeDataPoint({
    blobs: [
      JSON.stringify(event.signal),
      event.bundle_id,
      event.app_version,
      String(cf.country ?? 'unknown'),
      String(cf.asn ?? ''),
    ],
    indexes: ['pinning_bypass'],
  });

  // Optionally block token issuance for this device
  // by flagging the device fingerprint in KV
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  await env.KV_SECURITY.put(
    `pinning_bypass:${ip}`,
    JSON.stringify({ ...event, ip }),
    { expirationTtl: 3600 }
  );

  return new Response(null, { status: 202 });
}
```

## Workers: Block Token Issuance for Flagged Devices

```typescript
// workers/src/auth/tokenGuard.ts
export async function checkPinningBypassFlag(
  request: Request,
  env: Env
): Promise<boolean> {
  const ip = request.headers.get('CF-Connecting-IP') ?? '';
  if (!ip) return false;

  const flagged = await env.KV_SECURITY.get(`pinning_bypass:${ip}`);
  return flagged !== null;
}

// In the token issuance handler:
export async function handleTokenRequest(
  request: Request,
  env: Env
): Promise<Response> {
  if (await checkPinningBypassFlag(request, env)) {
    return Response.json(
      { error: 'device_integrity_failed' },
      { status: 403 }
    );
  }
  // ... normal token issuance
}
```

---

## Anti-patterns

- **Relying solely on client-side bypass detection** — an attacker with root can patch your binary. Client detection is a deterrent and an audit signal, not a security boundary. App Attest is the only hardware-rooted guarantee.
- **Crashing on bypass detection** — aggressive responses train attackers to patch the detector. Report silently and degrade gracefully; crashing apps get patched faster.
- **Using the pinned session to send the bypass report** — if the session is being intercepted, the report also fails. Use `URLSession.shared` (system TLS, no pinning) for reporting.
- **Pinning only the leaf certificate** — leaf certs rotate more frequently than intermediates. Pin SPKI hashes of 2–3 levels; include a backup hash to avoid locking yourself out on rotation.

---

## Gotchas

- **TestFlight builds** — App Attest attestation fails in TestFlight with the `development` environment; use `DCAppAttestService.Environment.development` during internal testing.
- **Certificate rotation** — you must ship the new hash in an app update before rotating the live cert, or pin the SPKI of the intermediate CA instead of the leaf.
- **`_dyld_image_count` on iOS 18+** — the value includes system dylibs which grew in iOS 18 (DriverKit, RealityKit, etc.). Calibrate the threshold on a clean device before shipping.
- **Workers KV TTL** — the 1-hour TTL on `pinning_bypass:` keys means a device is unblocked after 60 min. For persistent blocking, use D1 with a `device_blocks` table keyed by a stable device ID.

---

## Verification

```bash
# Confirm events are arriving in Analytics Engine
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d "SELECT blob1, count() FROM example project WHERE index1='pinning_bypass' GROUP BY blob1 LIMIT 10"

# Simulate bypass report from device
curl -X POST https://api.example.com/security/pinning-event \
  -H 'Content-Type: application/json' \
  -d '{"signal":{"sslKillSwitchDylib":{}},"bundle_id":"com.example.app","app_version":"1.0.0","timestamp":"2026-08-23T10:00:00Z"}'
# Expect 202
```

---

## Related

- `apple-app-attest-retry-and-risk-metric-preservation.md`
- `certificate-pinning.md`
- `jailbreak-root-detection.md`
- `mobile-jwt-storage-pitfalls.md`
- `cross-platform-app-attestation-device-integrity.md`

---

## Sources

- Apple App Attest — https://developer.apple.com/documentation/devicecheck/dcappattestservice
- SSL Kill Switch 2 — https://github.com/nabla-c0d3/ssl-kill-switch2
- OWASP Mobile Top 10 M3 Insecure Communication — https://owasp.org/www-project-mobile-top-10/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
