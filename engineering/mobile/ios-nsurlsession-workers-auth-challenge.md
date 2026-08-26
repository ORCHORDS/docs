# iOS NSURLSession Workers Auth Challenge

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

An iOS app making requests to a Cloudflare Workers endpoint receives repeated `401 Unauthorized` or stalls on a TLS handshake. `URLSession` delegates (`didReceive challenge`) are triggered unexpectedly — either from Cloudflare's mTLS enforcement, from a custom Workers authentication header pattern, or because the app is sending credentials in the wrong phase of the challenge-response cycle.

## Context

Cloudflare Workers support several authentication mechanisms that interact with `NSURLSession` differently: Bearer tokens (handled in the HTTP layer), Client certificates / mTLS (TLS layer, requires `URLAuthenticationChallenge`), and Workers-enforced Turnstile or custom HMAC headers (application layer). Each requires a distinct delegate response. This article covers JWT refresh on 401, mTLS with a certificate stored in the iOS Keychain, and how to avoid ATS (App Transport Security) pitfalls with Workers custom domains.

---

## URLSession Auth Delegate — JWT Refresh on 401

```swift
// Sources/Networking/WorkersSession.swift
import Foundation

final class WorkersSession: NSObject, URLSessionTaskDelegate {
  private let baseURL: URL
  private let tokenStore: TokenStore  // wraps Keychain

  private lazy var session: URLSession = {
    URLSession(configuration: .default, delegate: self, delegateQueue: nil)
  }()

  init(baseURL: URL, tokenStore: TokenStore) {
    self.baseURL = baseURL
    self.tokenStore = tokenStore
    super.init()
  }

  // MARK: - URLSessionTaskDelegate

  func urlSession(
    _ session: URLSession,
    task: URLSessionTask,
    didReceive challenge: URLAuthenticationChallenge,
    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
  ) {
    switch challenge.protectionSpace.authenticationMethod {

    case NSURLAuthenticationMethodServerTrust:
      // Standard TLS — let the system validate Cloudflare's cert
      completionHandler(.performDefaultHandling, nil)

    case NSURLAuthenticationMethodClientCertificate:
      // mTLS: load client cert from Keychain
      guard
        let identity = tokenStore.clientIdentity(),
        let cert = SecIdentityCopyCertificate(identity)
      else {
        completionHandler(.cancelAuthenticationChallenge, nil)
        return
      }
      let credential = URLCredential(
        identity: identity,
        certificates: [cert as Any],
        persistence: .forSession
      )
      completionHandler(.useCredential, credential)

    default:
      completionHandler(.performDefaultHandling, nil)
    }
  }

  // Handle 401 — refresh JWT and retry once
  func urlSession(
    _ session: URLSession,
    task: URLSessionTask,
    didCompleteWithError error: Error?
  ) {
    // HTTP 401 surfaces via response, not as an error; see makeRequest below
  }
}
```

---

## Authenticated Request with Automatic Token Refresh

```swift
// Sources/Networking/WorkersSession+Request.swift
extension WorkersSession {
  func makeRequest<T: Decodable>(
    path: String,
    method: String = "GET",
    body: Data? = nil,
    retryOn401: Bool = true
  ) async throws -> T {
    var request = URLRequest(url: baseURL.appendingPathComponent(path))
    request.httpMethod = method
    request.httpBody = body
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let token = try await tokenStore.validAccessToken()
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

    let (data, response) = try await session.data(for: request)

    guard let http = response as? HTTPURLResponse else {
      throw URLError(.badServerResponse)
    }

    if http.statusCode == 401 && retryOn401 {
      // Refresh via Workers /auth/refresh endpoint
      let newToken = try await refreshToken()
      request.setValue("Bearer \(newToken)", forHTTPHeaderField: "Authorization")
      let (retryData, retryResponse) = try await session.data(for: request)
      guard (retryResponse as? HTTPURLResponse)?.statusCode == 200 else {
        throw WorkersError.unauthorized
      }
      return try JSONDecoder().decode(T.self, from: retryData)
    }

    guard (200..<300).contains(http.statusCode) else {
      throw WorkersError.httpError(http.statusCode)
    }

    return try JSONDecoder().decode(T.self, from: data)
  }

  private func refreshToken() async throws -> String {
    let refreshToken = try tokenStore.refreshToken()
    var req = URLRequest(url: baseURL.appendingPathComponent("/auth/refresh"))
    req.httpMethod = "POST"
    req.httpBody = try JSONEncoder().encode(["refresh_token": refreshToken])
    req.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let (data, response) = try await session.data(for: req)
    guard (response as? HTTPURLResponse)?.statusCode == 200 else {
      throw WorkersError.refreshFailed
    }
    let result = try JSONDecoder().decode(RefreshResponse.self, from: data)
    try tokenStore.save(accessToken: <redacted-secret> refreshToken: result.refreshToken)
    return result.accessToken
  }
}
```

---

## Workers /auth/refresh Endpoint

```typescript
// workers/auth.ts
interface Env {
  JWT_SECRET: string;
  REFRESH_TOKENS: KVNamespace;
}

export async function handleRefresh(request: Request, env: Env): Promise<Response> {
  const { refresh_token } = await request.json<{ refresh_token: string }>();

  // Validate refresh token from KV (stored on login)
  const userId = await env.REFRESH_TOKENS.get(`rt:${refresh_token}`);
  if (!userId) {
    return new Response('Invalid refresh token', { status: 401 });
  }

  // Issue new access token (15-minute expiry)
  const newAccess = await signJWT({ sub: userId, exp: Date.now() / 1000 + 900 }, env.JWT_SECRET);
  // Rotate refresh token
  const newRefresh = crypto.randomUUID();
  await env.REFRESH_TOKENS.delete(`rt:${refresh_token}`);
  await env.REFRESH_TOKENS.put(`rt:${newRefresh}`, userId, { expirationTtl: 2_592_000 });

  return Response.json({ accessToken: newAccess, refreshToken: newRefresh });
}

async function signJWT(payload: object, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body   = btoa(JSON.stringify(payload));
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${header}.${body}`));
  return `${header}.${body}.${btoa(String.fromCharCode(...new Uint8Array(sig)))}`;
}
```

---

## App Transport Security (ATS) for Custom Workers Domains

```xml
<!-- ios/App/Info.plist -->
<key>NSAppTransportSecurity</key>
<dict>
  <!-- workers.dev and custom domains use valid TLS — no exceptions needed -->
  <!-- Only add exceptions for staging environments on non-standard ports -->
  <key>NSAllowsArbitraryLoadsInWebContent</key>
  <false/>
  <key>NSExceptionDomains</key>
  <dict>
    <!-- Example: internal staging Worker on a .workers.dev subdomain -->
    <key>staging.your-worker.workers.dev</key>
    <dict>
      <key>NSExceptionAllowsInsecureHTTPLoads</key>
      <false/>
      <key>NSIncludesSubdomains</key>
      <true/>
      <key>NSExceptionMinimumTLSVersion</key>
      <string>TLSv1.2</string>
    </dict>
  </dict>
</dict>
```

---

## Anti-patterns

- **Storing JWTs in `UserDefaults`** — use `SecItemAdd` / `SecItemCopyMatching` (Keychain) with `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`.
- **Implementing `performDefaultHandling` for client certificate challenges** — this silently skips mTLS and the Worker will reject the connection at the TCP layer with no HTTP error code.
- **Retrying 401 responses in an unbounded loop** — always gate refresh retries with a `retryOn401: Bool` flag and set it to `false` on the recursive call.
- **Ignoring `challenge.previousFailureCount`** — after 2–3 failures the system expects `cancelAuthenticationChallenge`; repeated `useCredential` responses cause an infinite loop that drains battery.

---

## Gotchas

- `URLSession` challenge delegates are called on an internal serial queue, not the main thread; never update UI directly inside the completion handler.
- Cloudflare mTLS requires the client certificate to chain to a CA uploaded via `wrangler mtls-certificate upload`. Self-signed certs not uploaded to Cloudflare are rejected at the edge, not in the challenge delegate.
- Workers behind Cloudflare Access (zero-trust) issue a 302 to an IdP login page, not a 401. Detect this by checking `response.url` for `cloudflareaccess.com` and handle as an OAuth redirect instead.
- The `NSURLAuthenticationMethodServerTrust` challenge fires even for valid Cloudflare certificates when your app uses certificate pinning. Make sure to call `SecTrustEvaluateAsyncWithError` before deciding.

---

## Verification

```swift
// Unit test: assert refresh flow
let mockSession = MockURLSession()
mockSession.enqueue(response: HTTPURLResponse(statusCode: 401))
mockSession.enqueue(response: HTTPURLResponse(statusCode: 200), data: tokenJSON)
mockSession.enqueue(response: HTTPURLResponse(statusCode: 200), data: resourceJSON)

let result: MyResource = try await workersSession.makeRequest(path: "/resource")
XCTAssertEqual(mockSession.requestCount, 3) // original + refresh + retry
```

```bash
# Confirm mTLS is enforced at Cloudflare edge
curl --cert client.crt --key client.key https://your-worker.workers.dev/mtls-protected
# Without cert should return 403, with cert 200
```

---

## Related

- `ios-workers-certificate-pinning-bypass-detection.md`
- `react-native-workers-biometric-auth-secure-enclave.md`
- `mobile-jwt-storage-pitfalls.md`
- `mobile-auth-oauth-pkce.md`
- `ios-urlsession-patterns.md`

---

## Sources

- Apple URLSession Authentication: https://developer.apple.com/documentation/foundation/url_loading_system/handling_an_authentication_challenge
- Cloudflare mTLS: https://developers.cloudflare.com/ssl/client-certificates/
- Cloudflare Access: https://developers.cloudflare.com/cloudflare-one/
- NSURLAuthenticationMethodClientCertificate: https://developer.apple.com/documentation/foundation/nsurlauthenticationmethodclientcertificate
