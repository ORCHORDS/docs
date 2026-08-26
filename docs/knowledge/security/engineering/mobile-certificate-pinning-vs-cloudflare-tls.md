# Mobile App Certificate Pinning vs Cloudflare Edge TLS

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A mobile app hardcodes (pins) the server's TLS certificate or public key to detect
man-in-the-middle (MitM) proxying. The team then routes all traffic through Cloudflare
for DDoS protection, WAF, and Bot Management — and the pins break. Or the Cloudflare
certificate rotates, and the app pins stop matching, taking the app offline for all
users on older builds. This article explains the collision, the correct pinning strategy
for Cloudflare-fronted APIs, and how to design the end-to-end trust chain so that
security is preserved while operational flexibility is maintained.

## Context

Certificate pinning exists to defeat a class of attacks where:
- A corporate proxy or parental control tool transparently MitMs TLS connections.
- Malware on a rooted/jailbroken device installs a rogue CA into the OS trust store.
- A compromised or mis-issuing CA issues a fraudulent certificate for your domain.

When your API sits behind Cloudflare, the TLS connection from the mobile client
terminates at Cloudflare's edge, not at your origin. The certificate the client sees
is Cloudflare's managed certificate (or your custom certificate uploaded to Cloudflare).
A second TLS connection — origin pull — runs between Cloudflare and your server; the
mobile client never sees the origin certificate.

This creates two distinct pinning targets:
1. **Edge certificate** (Cloudflare's): what the mobile client can pin.
2. **Origin pull certificate**: irrelevant to the mobile client.

Attack vectors relevant to this architecture:
- **Enterprise MitM**: corporate MDM installs a trusted root; all employee devices are
  transparently proxied. Pinning defeats this but may be a policy conflict.
- **BGP hijack + fraudulent cert**: an attacker reroutes traffic and uses a misissued
  certificate. Pinning defeats this even if the rogue cert chains to a trusted CA.
- **Cloudflare account compromise**: if an attacker gains access to your Cloudflare
  account, they could issue a new certificate; pinning to a key set rather than a
  single cert provides rotation safety.
- **Supply chain compromise of Cloudflare CA**: Cloudflare's edge certificates are
  issued by DigiCert, Let's Encrypt, or Google Trust Services. Pinning to one of their
  intermediate keys means rotating among them breaks the pin.

## What Can Be Pinned with Cloudflare

### Option A: Pin Cloudflare Root CAs (Weakest, Most Flexible)

Pin to the set of CAs that Cloudflare uses to issue edge certificates. As of 2026:
- DigiCert Global Root G2
- ISRG Root X1 (Let's Encrypt)
- GTS Root R1 (Google Trust Services)

Pros: certificates can rotate freely at the edge; pins only break if Cloudflare
switches root CA providers (rare, announced in advance).
Cons: provides very weak guarantees — any certificate from those roots (millions) would
pass pinning.

### Option B: Pin the Subject Public Key Info (SPKI) of Cloudflare Intermediate CAs

Cloudflare's intermediates are more stable than leaf certificates. Pin to SPKI hashes
of the two or three intermediates currently in use, plus at least one backup.

Derive the hash:

```bash
# Retrieve the certificate chain Cloudflare presents for your domain
openssl s_client -connect api.example.com:443 -showcerts </dev/null 2>/dev/null \
  | awk '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/' \
  | csplit -z - '/-----BEGIN CERTIFICATE-----/' '{*}' --prefix=cert --suffix-format=%02d.pem

# For each intermediate cert (cert01.pem, cert02.pem, …):
openssl x509 -in cert01.pem -noout -pubkey \
  | openssl pkey -pubin -outform der \
  | openssl dgst -sha256 -binary \
  | base64
```

Store multiple hashes: the leaf, each intermediate, and a backup.

### Option C: Cloudflare Custom Certificates with Your Own Key Pair (Strongest)

Upload your own certificate and private key to Cloudflare (Custom Certificates feature).
You control the key pair; you pin to its SPKI hash. Certificate rotation requires
uploading a new cert with the same key (or updating the pin in a future app build).

For SPKI pinning to survive certificate renewal without an app update, use the same
key pair for renewals (key-pinning semantics).

## iOS Implementation (NSURLSession + TrustKit)

TrustKit is the recommended library for iOS SPKI pinning as it handles the
`SecTrustEvaluateWithError` complexity:

```swift
// AppDelegate.swift
import TrustKit

func application(
  _ application: UIApplication,
  didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
) -> Bool {

  let trustKitConfig: [String: Any] = [
    kTSKSwizzleNetworkDelegates: false,     // use explicit delegate, not swizzling
    kTSKPinnedDomains: [
      "api.example.com": [
        kTSKEnforcePinning: true,
        kTSKIncludeSubdomains: false,
        kTSKExpirationDate: "2027-01-01",   // forces pin review before expiry
        kTSKPublicKeyHashes: [
          // Current Cloudflare intermediate SPKI hash
          "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
          // Backup intermediate hash
          "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=",
          // Emergency fallback (root)
          "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC=",
        ],
        kTSKReportUris: ["https://api.example.com/pin-failure-reports"],
      ],
    ],
  ]
  TrustKit.initSharedInstance(withConfiguration: trustKitConfig)
  return true
}
```

```swift
// NetworkClient.swift — explicit delegate, not swizzle
class PinnedURLSessionDelegate: NSObject, URLSessionDelegate {
  func urlSession(
    _ session: URLSession,
    didReceive challenge: URLAuthenticationChallenge,
    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
  ) {
    if TrustKit.sharedInstance().pinningValidator.handle(challenge, completionHandler: completionHandler) {
      return
    }
    // Default handling for non-server-trust challenges
    completionHandler(.performDefaultHandling, nil)
  }
}
```

## Android Implementation (Network Security Config)

Android's declarative pinning in `network_security_config.xml` is the most
maintainable approach:

```xml
<!-- res/xml/network_security_config.xml -->
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <domain-config cleartextTrafficPermitted="false">
    <domain includeSubdomains="false">api.example.com</domain>
    <pin-set expiration="2027-01-01">
      <!-- Current Cloudflare intermediate SPKI (SHA-256, base64) -->
      <pin digest="SHA-256">AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=</pin>
      <!-- Backup: second intermediate or root -->
      <pin digest="SHA-256">BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=</pin>
    </pin-set>
    <trustkit-config enforcePinning="true"
      reportUri="https://api.example.com/pin-failure-reports" />
  </domain-config>
</network-security-config>
```

```xml
<!-- AndroidManifest.xml -->
<application
  android:networkSecurityConfig="@xml/network_security_config"
  ...>
```

## Pin Failure Reporting (Workers endpoint)

Collect pin failure telemetry to detect attacks or misconfiguration before users
are locked out:

```typescript
// POST /pin-failure-reports
export async function handlePinFailureReport(
  request: Request,
  env: Env,
): Promise<Response> {
  // TrustKit sends reports as JSON with Content-Type: application/json
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  let report: unknown;
  try {
    report = await request.json();
  } catch {
    return new Response('Bad Request', { status: 400 });
  }

  // Log to Analytics Engine or a D1 table for alerting
  await env.DB.prepare(
    `INSERT INTO pin_failure_reports (app_bundle, hostname, failed_pins, known_pins, ts)
     VALUES (?1, ?2, ?3, ?4, datetime('now'))`,
  )
    .bind(
      (report as any)?.app_bundle_id ?? 'unknown',
      (report as any)?.hostname ?? 'unknown',
      JSON.stringify((report as any)?.failed_pins ?? []),
      JSON.stringify((report as any)?.known_pins ?? []),
    )
    .run();

  // Alert if > 10 unique devices report failures in 5 minutes — indicates cert change
  await checkAndAlertPinFailureSurge(env);

  return new Response(null, { status: 204 });
}
```

## Managing Pin Transitions Safely

1. **Deploy new pins in report-only mode**: TrustKit supports `kTSKEnforcePinning: false`
   with reporting enabled. Ship a build that logs failures but does not block traffic.
   Monitor for unexpected failures.
2. **Ship the backup pin before you need it**: include the new intermediate/key SPKI
   as a backup pin in the current production build. The backup is never matched until
   the primary cert rotates.
3. **Wait for old builds to roll off**: use App Store Connect / Play Console metrics
   to confirm >95% of sessions run the backup-enabled build before switching the
   certificate.
4. **Switch the certificate** at the edge (Cloudflare dashboard or API). The backup
   pin now becomes the primary match; the old primary becomes orphaned but harmless.
5. **Ship a follow-up build** that removes the old primary pin and adds a new backup
   for the next rotation.

This rolling approach ensures no live user is ever pin-locked during a transition.

## Cloudflare-Specific Considerations

- **Cloudflare certificate auto-renewal**: Cloudflare renews edge certificates
  automatically. For Universal SSL (managed certs), the intermediate CA may change
  between renewals. If you pin to a specific intermediate, set `expiration` in your
  pin config to a date before the certificate's expiry to force a pin review.
- **Cloudflare mTLS for client authentication**: if you use Cloudflare mTLS (client
  certificates), the trust anchor is your own CA, not Cloudflare's. Pin to your
  CA's root key instead of Cloudflare's intermediates.
- **Argo Smart Routing / Tiered Cache**: these do not affect the certificate presented
  at the edge; pinning behaviour is unchanged.
- **Workers routes and Custom Domains**: Workers served from `*.workers.dev` present
  Cloudflare's `workers.dev` wildcard certificate. If your mobile app calls a Worker
  at a custom domain, it sees your custom-domain certificate.

## Anti-patterns

- **Pinning the leaf certificate by certificate hash**: the leaf cert rotates every
  90 days (Let's Encrypt) to 1–2 years (DigiCert). Leaf pinning requires a coordinated
  app release with every certificate renewal. Use SPKI (public key) pinning instead.
- **Storing pins only in runtime code (not NSC)**: on Android, runtime-only pinning
  can be bypassed by root + Frida hooking before the app's `SSLSocketFactory` is
  initialised. The OS-level `network_security_config.xml` enforcement happens in a
  lower layer.
- **No backup pin**: if the active pin is the only pin and the certificate changes
  (planned or emergency), all deployed app versions are locked out until a new build
  propagates. Always ship at least two pins.
- **Not pinning in debug builds**: disable enforcement in debug, but keep reporting on.
  This lets test environments use Charles Proxy while production traffic remains pinned.
- **Pinning the Cloudflare root without any intermediate**: provides only marginally
  stronger assurance than no pinning at all. Aim for intermediate-level pins at minimum.

## Gotchas

- iOS App Transport Security (ATS) does its own certificate validation before your
  TrustKit delegate is called. If ATS is disabled (`NSAllowsArbitraryLoads: true`),
  pinning still works but you lose OS-level TLS enforcement.
- Android `network_security_config.xml` pins apply to all network traffic for the
  app, including third-party SDKs embedded in the app (analytics, crash reporters).
  If those SDKs use different domains, ensure those domains are not pinned or have
  their own correct pin entries.
- Cloudflare Waiting Room and other Cloudflare features may redirect HTTP requests to
  HTTPS. The redirect itself (HTTP 301) is not subject to TLS pinning; ensure your
  mobile client follows to the HTTPS URL where pinning applies.
- React Native's `fetch` uses the OS networking stack on iOS and Android, so
  `network_security_config.xml` pins apply automatically on Android. On iOS you must
  explicitly wire TrustKit into the URL session used by React Native's network layer.

## Verification

```bash
# Extract and display the SPKI hash for the cert currently served by your domain
openssl s_client -connect api.example.com:443 </dev/null 2>/dev/null \
  | openssl x509 -noout -pubkey \
  | openssl pkey -pubin -outform der \
  | openssl dgst -sha256 -binary \
  | base64

# Simulate a pin mismatch (test environment with mkcert)
# Set up a local proxy with a self-signed cert and point the test device to it.
# The app should log a pin failure report to /pin-failure-reports.
# Check your D1 table:
wrangler d1 execute my-db \
  --command "SELECT * FROM pin_failure_reports ORDER BY ts DESC LIMIT 10"
```

## Related

- `tls-certificate-lifecycle-management.md`
- `cloudflare-zero-trust-mtls-service-auth.md`
- `oauth-pkce-mobile-cloudflare-workers.md`
- `jwt-storage-mobile-workers-auth.md`
- `certificate-transparency-v2-log-proof-validation.md`
- `tls-13-early-data-0rtt-replay-safe-endpoint-policy.md`

## Sources

- TrustKit (iOS/Android): https://github.com/datatheorem/TrustKit
- Android Network Security Configuration: https://developer.android.com/privacy-and-security/security-config
- RFC 7469 — HTTP Public Key Pinning (historical, deprecated but informative): https://www.rfc-editor.org/rfc/rfc7469
- Cloudflare Custom Certificates: https://developers.cloudflare.com/ssl/edge-certificates/custom-certificates/
- OWASP Mobile Application Security Testing Guide — Network Communication: https://mas.owasp.org/MASTG/
