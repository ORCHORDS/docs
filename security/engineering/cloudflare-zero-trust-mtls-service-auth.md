# cloudflare-zero-trust-mtls-service-auth

**Issue:** mTLS between example project Workers and internal services
fails on mobile clients due to certificate pinning mismatches
and different TLS stack behaviors on iOS vs Android, while
service-to-service mTLS needs correct Zero Trust policy scope
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented — example project project (Zero Trust, mobile)

## Symptom

Internal Worker-to-Worker requests authenticated via mTLS
succeed from the Cloudflare network but fail when the mobile
app is the initiating party. On iOS, certificate validation
errors (`NSURLErrorServerCertificateUntrusted`) appear when
the app presents a client certificate for a mutual TLS endpoint.
On Android, OkHttp throws `SSLHandshakeException` when the
pinned certificate chain does not match the Zero Trust CA.

## Context

example project uses Cloudflare Zero Trust mTLS in two ways:

1. **Service-to-service:** Worker A calls Worker B through a
   Zero Trust Access policy requiring a client certificate
   issued by the example project internal CA.
2. **Mobile-to-Worker:** The React Native app presents a per-
   device certificate to the Worker for high-trust operations
   (age verification re-check, content reporting) where JWT
   authentication alone is insufficient.

These two surfaces have different certificate management
requirements and behave differently across iOS and Android.

## mTLS architecture overview

```
+----------+     mTLS      +------------------+
| Worker A |  -----------> | CF Zero Trust     |
|          |  client cert  | Access Application|
+----------+               | policy: cert CN   |
                           |  matches service  |
                           +--------+----------+
                                    |
                                    v (if cert valid)
                           +------------------+
                           | Worker B (origin)|
                           +------------------+

+------------------+   mTLS   +------------------+
| React Native App |  ------> | CF Zero Trust     |
| (per-device cert)|          | Access Application|
+------------------+          | policy: cert OU  |
                              |  = "example project-mobile"  |
                              +--------+----------+
                                       |
                                       v
                              +------------------+
                              | Worker (API)     |
                              +------------------+
```

## Issuing certificates via Cloudflare Zero Trust

Cloudflare Zero Trust can act as a CA for mTLS. Issue
certificates from the dashboard or via the API:

```bash
# Create a client CA in Zero Trust
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCT}/access/mtls/certificates" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "example project-mobile-ca",
    "certificate": "'"$(cat example project-mobile-ca.pem)"'",
    "associated_hostnames": ["api.example project.app"]
  }'

# The response includes a certificate_id to use in Access policies
```

```bash
# Issue a device certificate signed by the mobile CA
openssl req -new -newkey rsa:2048 -nodes \
  -keyout device-client.key \
  -out device-client.csr \
  -subj "/CN=device-$(uuidgen)/OU=example project-mobile/O=example.com"

openssl x509 -req -in device-client.csr \
  -CA example project-mobile-ca.pem -CAkey example project-mobile-ca.key \
  -CAcreateserial -out device-client.crt -days 365 \
  -sha256
```

In the Zero Trust Access application policy, require:
`Certificate OU = example project-mobile` to scope it to mobile clients
only, separate from service-to-service Worker certificates.

## Workers client certificate validation

Workers can read the client certificate that Cloudflare's
mTLS layer has already validated. The certificate details
arrive in request headers:

```ts
// Worker — validate mTLS client certificate attributes
export async function handleMtlsRequest(
  request: Request,
  env: Env
): Promise<Response> {
  // Cloudflare sets these after mTLS validation
  // (only present when Access policy passed)
  const clientCertCN = request.headers.get(
    "Cf-Access-Authenticated-User-Email"  // for human certs
  );
  const certPresented = request.headers.get(
    "X-Client-Certificate-Presented"
  );

  // For service-to-service, use CF Access service token headers
  const clientId = request.headers.get("Cf-Access-Client-Id");
  const clientSecret = <redacted-secret>"Cf-Access-Client-Secret");

  if (!clientId || !clientSecret) {
    return new Response("Unauthorized", { status: 401 });
  }

  // Validate the service token against expected values
  if (
    clientId !== env.EXPECTED_SERVICE_CLIENT_ID ||
    !timingSafeEqual(clientSecret, env.EXPECTED_SERVICE_CLIENT_SECRET)
  ) {
    return new Response("Forbidden", { status: 403 });
  }

  // At this point, Cloudflare has already validated the mTLS cert
  // and the Access policy. Proceed with the request.
  return processServiceRequest(request, env);
}
```

For mobile clients, read the forwarded certificate attributes
from the `Cf-Access-*` headers that Zero Trust populates after
evaluating the certificate-based policy.

## iOS certificate pinning with mTLS

iOS URLSession does not natively support loading PKCS#12 client
certificates from the file system at runtime without a custom
`URLSessionDelegate`. Use a `SecIdentity` from the Keychain:

```swift
// iOS — load client certificate from Keychain and present
// in URLSession for mTLS
class MtlsSessionDelegate: NSObject, URLSessionDelegate {
  func urlSession(
    _ session: URLSession,
    didReceive challenge: URLAuthenticationChallenge,
    completionHandler: @escaping (URLSession.AuthChallengeDisposition,
      URLCredential?) -> Void
  ) {
    guard challenge.protectionSpace.authenticationMethod ==
      NSURLAuthenticationMethodClientCertificate else {
        completionHandler(.performDefaultHandling, nil)
        return
    }
    // Load identity from Keychain (provisioned at onboarding)
    if let identity = loadClientIdentityFromKeychain() {
      let credential = URLCredential(
        identity: identity,
        certificates: nil,
        persistence: .forSession
      )
      completionHandler(.useCredential, credential)
    } else {
      completionHandler(.cancelAuthenticationChallenge, nil)
    }
  }
}
```

The `SecIdentity` (private key + certificate pair) must be
imported into the Keychain during device provisioning, not
shipped in the app bundle. Generate and provision via the
Worker during age verification completion.

## Android certificate pinning with OkHttp + mTLS

```kotlin
// Android — OkHttp with client certificate from Android Keystore
fun buildMtlsClient(context: Context): OkHttpClient {
  val keyStore = KeyStore.getInstance("AndroidKeyStore").apply {
    load(null)
  }
  // Certificate alias provisioned during onboarding
  val alias = "example project_device_cert"
  val entry = keyStore.getEntry(alias, null)
    as? KeyStore.PrivateKeyEntry
    ?: error("Device certificate not provisioned")

  val kmf = KeyManagerFactory
    .getInstance(KeyManagerFactory.getDefaultAlgorithm())
    .apply {
      val ks = KeyStore.getInstance(KeyStore.getDefaultType()).apply {
        load(null)
        setKeyEntry(alias, entry.privateKey, null, entry.certificateChain)
      }
      init(ks, null)
    }

  val sslContext = SSLContext.getInstance("TLS").apply {
    init(kmf.keyManagers, null, null)
  }

  return OkHttpClient.Builder()
    .sslSocketFactory(sslContext.socketFactory,
      sslContext.trustManager as X509TrustManager)
    .build()
}
```

The Android Keystore holds private key material in hardware
(TEE or StrongBox) on supported devices. The key never leaves
the secure element, unlike PKCS#12 files stored on disk.

## iOS vs Android certificate handling differences

```
+----------------------+------------------+--------------------+
| Aspect               | iOS              | Android            |
+----------------------+------------------+--------------------+
| Secure storage       | Keychain         | Android Keystore   |
| Hardware backed      | Secure Enclave   | TEE / StrongBox    |
| Certificate format   | SecIdentity      | KeyStore.Entry     |
| Import mechanism     | PKCS12 / Keychain| PKCS12 / Keystore  |
| iCloud sync          | Optional (avoid) | No                 |
| Backup               | Opt-out required | Never backed up    |
| mTLS client hello    | URLSessionDelegate| X509KeyManager    |
| OS version risk      | iOS 15+ needed   | API 23+ needed     |
+----------------------+------------------+--------------------+
```

Both platforms should provision the certificate on first app
launch via a Workers endpoint that requires JWT + OTP, stores
the issued cert in the platform secure store, and never
exposes the private key outside the device.

## Anti-patterns

- Shipping a client certificate in the app bundle (`.p12` file
  in assets) — it is extractable from any APK/IPA and can be
  used by any device, defeating per-device authentication.
- Using the same CA and certificate for both service-to-service
  and mobile clients — if a device cert is compromised, it
  could impersonate a service. Use separate CAs and Access
  policies for each trust domain.
- Configuring the Access application policy to accept any valid
  certificate from the CA without validating CN or OU — too
  broad; require the device-specific CN for mobile certs.
- Disabling server certificate validation on the mobile client
  to work around pinning issues during development — use a
  `DEBUG` flag and never ship with validation disabled.
- Storing the PKCS#12 passphrase in `BuildConfig` or
  `Info.plist` — it can be extracted from the binary.

## Gotchas

- Cloudflare Zero Trust mTLS is evaluated before the request
  reaches the Worker. If the Access policy blocks a request,
  the Worker never runs and you cannot log the rejection in
  Worker code. Set up Access logging to a Log Push destination
  (R2 or an external SIEM) to capture mTLS rejections.
- Certificate renewal on mobile requires the app to be active.
  If a user does not open the app before their device cert
  expires (1 year), they will be locked out of high-trust
  operations. Implement a 30-day pre-expiry in-app prompt.
- iOS Keychain items with `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly`
  are deleted when the user removes their device passcode.
  Use `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`
  for mTLS certs to survive passcode changes.
- Android Keystore keys generated with `setUserAuthenticationRequired(true)`
  require biometric re-auth periodically. For background mTLS
  (Worker-to-Worker, not user-initiated), disable this flag.

## Verification

- Service-to-service: Worker A → Worker B request via Zero
  Trust — confirm `200` with correct Access headers in logs
- Mobile mTLS: send request without client cert →
  Cloudflare returns `403` before Worker executes
- Mobile mTLS: send request with valid device cert →
  Worker receives request with `Cf-Access-*` headers set
- Confirm cert not in app bundle: `unzip -l app.ipa | grep p12`
  → no results
- Check Access audit log for mTLS events over 24 h; confirm
  all entries have matching device CN values

## Related

- `security/cloudflare-access-service-token-rotation-and-emergency-revocation.md`
- `security/cloudflare-waf-mobile-api-false-positives.md`
- `security/jwt-storage-mobile-workers-auth.md`
- `cloudflare/workers-request-lifecycle.md`
- `mobile/react-native-http-client-config.md`

## Sources

- https://developers.cloudflare.com/cloudflare-one/identity/devices/mutual-tls-authentication/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/private-net/mtls/
- https://developer.apple.com/documentation/foundation/urlsession
- https://developer.android.com/training/articles/keystore
- https://www.rfc-editor.org/rfc/rfc8705 (OAuth 2.0 mTLS)
