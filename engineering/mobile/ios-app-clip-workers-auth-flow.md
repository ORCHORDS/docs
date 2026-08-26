# iOS App Clip Workers Lightweight Auth Flow

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A business wants users who scan an NFC tag or QR code to immediately access a checkout, loyalty
check-in, or event ticket flow without installing the full app. The App Clip must authenticate the
user, call a Cloudflare Workers API for business logic, and optionally hand off a session token to
the full app after install. Developers hit pain points around the 15 MB size limit, Keychain
sharing between clip and full app, and correctly scoping the Workers auth token to the App Clip
invocation URL.

## Context

App Clips are ephemeral app instances launched from a URL (App Clip Code, NFC, QR, Safari banner,
Messages). They run in a sandboxed container with a separate bundle ID suffix (`.Clip`) and cannot
use most entitlements available to the full app — notably no Push Notifications, no background
fetch, and no CloudKit. Auth must be lightweight: Sign in with Apple (recommended) or a one-time
code flow, with the session token persisted in a shared Keychain access group so the full app
inherits it on install.

Cloudflare Workers serves as the token-issuing authority: the App Clip POSTs its identity proof,
and the Worker issues a short-lived JWT stored in D1 alongside the clip invocation context.

Stack:
- Swift 5.9 + SwiftUI (App Clip target)
- Sign in with Apple (`AuthenticationServices`)
- Cloudflare Workers (token issuance, business logic)
- Cloudflare D1 (session + redemption state)
- Shared Keychain access group

## Cloudflare Worker: App Clip Token Issuance

```typescript
// worker/src/clipAuth.ts
import { Env } from './types';
import { verifyAppleIdentityToken } from './appleAuth';

export async function handleClipAuth(
  request: Request,
  env: Env,
): Promise<Response> {
  const { appleIdentityToken, invocationUrl, clipNonce } = await request.json<{
    appleIdentityToken: string;
    invocationUrl: string;
    clipNonce: string;
  }>();

  // Validate the Sign in with Apple identity token against Apple's JWKS
  const appleUser = await verifyAppleIdentityToken(appleIdentityToken, env.APPLE_CLIENT_ID);
  if (!appleUser) {
    return new Response(JSON.stringify({ error: 'Invalid Apple identity token' }), {
      status: 401,
    });
  }

  // Parse the invocation URL to determine the business context (e.g., table ID, event ID)
  const url = new URL(invocationUrl);
  const contextId = url.searchParams.get('id') ?? url.pathname.split('/').pop() ?? 'unknown';

  // Issue a short-lived clip session token (15 minutes)
  const sessionId = crypto.randomUUID();
  const expiresAt = new Date(Date.now() + 15 * 60 * 1000).toISOString();

  await env.DB.prepare(
    `INSERT INTO clip_sessions (session_id, apple_user_id, context_id, clip_nonce, expires_at, created_at)
     VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`,
  )
    .bind(sessionId, appleUser.sub, contextId, clipNonce, expiresAt)
    .run();

  // Sign a JWT — in production use a Workers KV-backed signing key
  const payload = {
    sub: appleUser.sub,
    sid: sessionId,
    ctx: contextId,
    exp: Math.floor(Date.now() / 1000) + 900,
    iss: 'clip-auth',
  };

  const token = await signJwt(payload, env.CLIP_JWT_SECRET);

  return new Response(JSON.stringify({ token, sessionId, expiresAt, contextId }), {
    headers: { 'Content-Type': 'application/json' },
  });
}

async function signJwt(payload: object, secret: string): Promise<string> {
  const header = { alg: 'HS256', typ: 'JWT' };
  const encode = (obj: object) =>
    btoa(JSON.stringify(obj)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const unsigned = `${encode(header)}.${encode(payload)}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(unsigned));
  const b64sig = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `${unsigned}.${b64sig}`;
}
```

```sql
-- D1 schema
CREATE TABLE IF NOT EXISTS clip_sessions (
  session_id   TEXT PRIMARY KEY,
  apple_user_id TEXT NOT NULL,
  context_id   TEXT NOT NULL,
  clip_nonce   TEXT NOT NULL,
  expires_at   TEXT NOT NULL,
  redeemed_at  TEXT,
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clip_sessions_user ON clip_sessions(apple_user_id);
```

## App Clip Swift Auth Flow

```swift
// AppClipAuthView.swift
import SwiftUI
import AuthenticationServices

struct AppClipAuthView: View {
    @StateObject private var authVM = ClipAuthViewModel()

    var body: some View {
        VStack(spacing: 24) {
            if authVM.isLoading {
                ProgressView("Signing in…")
            } else if let error = authVM.error {
                Text(error).foregroundColor(.red).multilineTextAlignment(.center)
                Button("Try Again") { authVM.reset() }
            } else if authVM.isAuthenticated {
                ClipContentView(token: authVM.sessionToken!)
            } else {
                SignInWithAppleButton(.signIn) { request in
                    request.requestedScopes = [.email, .fullName]
                    request.nonce = authVM.nonce
                } onCompletion: { result in
                    authVM.handleAppleSignIn(result: result)
                }
                .signInWithAppleButtonStyle(.black)
                .frame(height: 50)
            }
        }
        .padding()
        .onAppear { authVM.prepareNonce() }
    }
}
```

```swift
// ClipAuthViewModel.swift
import Foundation
import AuthenticationServices
import Security
import CryptoKit

@MainActor
final class ClipAuthViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var isAuthenticated = false
    @Published var error: String?
    @Published var sessionToken: String?

    private(set) var nonce: String = ""
    private let workerBase = "https://api.example.workers.dev"
    // Keychain access group shared with the full app target
    private let keychainGroup = "TEAMID.com.example.app.shared"

    func prepareNonce() {
        // SHA-256 hashed nonce for Apple — prevents replay attacks
        let raw = UUID().uuidString
        nonce = raw
    }

    func handleAppleSignIn(result: Result<ASAuthorization, Error>) {
        switch result {
        case .failure(let err):
            error = err.localizedDescription
        case .success(let auth):
            guard let credential = auth.credential as? ASAuthorizationAppleIDCredential,
                  let identityTokenData = credential.identityToken,
                  let identityToken = String(data: identityTokenData, encoding: .utf8)
            else {
                error = "Missing identity token from Apple"
                return
            }
            Task { await authenticateWithWorker(identityToken: identityToken) }
        }
    }

    private func authenticateWithWorker(identityToken: String) async {
        isLoading = true
        defer { isLoading = false }

        // Read the App Clip invocation URL from UserActivity (set in AppClip entry point)
        let invocationUrl = UserDefaults(suiteName: "group.com.example.app")?.string(forKey: "clipInvocationURL") ?? ""

        do {
            var request = URLRequest(url: URL(string: "\(workerBase)/clip/auth")!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode([
                "appleIdentityToken": identityToken,
                "invocationUrl": invocationUrl,
                "clipNonce": nonce,
            ])

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                throw NSError(domain: "ClipAuth", code: -1, userInfo: [NSLocalizedDescriptionKey: "Auth failed"])
            }

            let body = try JSONDecoder().decode(ClipAuthResponse.self, from: data)
            sessionToken = body.token

            // Persist to shared Keychain so the full app can inherit the session
            saveToSharedKeychain(token: body.token, sessionId: body.sessionId)
            isAuthenticated = true

        } catch {
            self.error = error.localizedDescription
        }
    }

    private func saveToSharedKeychain(token: String, sessionId: String) {
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: "com.example.app.clipSession",
            kSecAttrAccount: "sessionToken",
            kSecValueData: Data(token.utf8),
            kSecAttrAccessGroup: keychainGroup,
            kSecAttrAccessible: kSecAttrAccessibleAfterFirstUnlock,
        ]
        SecItemDelete(query as CFDictionary) // remove old value
        SecItemAdd(query as CFDictionary, nil)
    }

    func reset() { error = nil; isAuthenticated = false; sessionToken = nil }
}

struct ClipAuthResponse: Decodable {
    let token: String
    let sessionId: String
    let expiresAt: String
    let contextId: String
}
```

## Handoff to Full App

After the full app is installed, read the Keychain token in the full app's `AppDelegate`:

```swift
// Full app: inherit App Clip session
func readClipSessionFromKeychain() -> String? {
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: "com.example.app.clipSession",
        kSecAttrAccount: "sessionToken",
        kSecAttrAccessGroup: "TEAMID.com.example.app.shared",
        kSecReturnData: true,
        kSecMatchLimit: kSecMatchLimitOne,
    ]
    var result: AnyObject?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess, let data = result as? Data else { return nil }
    return String(data: data, encoding: .utf8)
}
```

## Anti-patterns

- **Storing the session token in `UserDefaults` instead of Keychain** — `UserDefaults` is not
  encrypted and is not accessible via shared app groups on App Clip containers.
- **Long-lived tokens for App Clip sessions** — App Clips are ephemeral; issue tokens expiring in
  ≤ 15 minutes, refreshable only by the full app after install.
- **Requesting unnecessary Sign in with Apple scopes** — App Clips should request only what the
  clip flow needs. Requesting `.email` and `.fullName` when only identity is needed adds friction.
- **Using `WKWebView` for the auth flow** — Adds WebKit overhead that pushes the clip past 15 MB
  faster. Use native SwiftUI for all UI in the clip.
- **Not hashing the nonce** — Apple requires the SHA-256 hash of the nonce in the token request;
  sending the raw nonce causes validation failures.

## Gotchas

- App Clip containers are deleted when the user has not opened the clip for 30 days; Keychain
  items in the shared access group persist across this deletion.
- The App Clip target must have the same `App Groups` and `Keychain Sharing` entitlements as the
  full app, with the same values — mismatches cause `errSecItemNotFound` on handoff.
- Sign in with Apple identity tokens expire in 10 minutes. Validate them in the Worker within
  seconds of issuance to avoid expiry races.
- Workers KV is the right store for the Apple JWKS cache (TTL 24 h); avoid fetching
  `https://appleid.apple.com/auth/keys` on every clip auth request.

## Verification

```bash
# Test Worker auth endpoint
curl -X POST https://api.example.workers.dev/clip/auth \
  -H 'Content-Type: application/json' \
  -d '{"appleIdentityToken":"<test_token>","invocationUrl":"https://example.com/table?id=42","clipNonce":"abc123"}'

# Verify session in D1
npx wrangler d1 execute clip-db \
  --command "SELECT session_id, context_id, expires_at FROM clip_sessions ORDER BY created_at DESC LIMIT 5;"
```

Test the full handoff flow using Xcode's App Clip Experiences in the simulator:
Scheme → Run → Arguments → `_XCAppClipURL=https://example.com/table?id=42`

## Related

- `ios-app-clips.md`
- `ios-keychain-storage.md`
- `mobile-auth-oauth-pkce.md`
- `ios-push-notifications-apns-workers.md`
- `mobile-webauthn-workers-credential-storage.md`

## Sources

- https://developer.apple.com/documentation/app_clips
- https://developer.apple.com/documentation/authenticationservices/sign_in_with_apple
- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/d1/
- https://developer.apple.com/documentation/security/keychain_services
