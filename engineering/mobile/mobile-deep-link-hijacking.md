# mobile-deep-link-hijacking

**Issue:** iOS Universal Links / Android App Links hijacking, custom URI scheme attacks, OAuth callback theft, Cloudflare Worker serving /.well-known/
**Date:** 2026-08-11
**Status:** documented

## Symptom
Your app uses `example project://oauth/callback` as the OAuth redirect URI.
A malicious app on the same device registers the same scheme and
intercepts the authorization code. On iOS, your Universal Link
falls back to Safari when the app is not installed, leaking the token
in the browser history. The App Links verification JSON returns a
wrong-format response and Android falls back to the browser.

## Root cause
**Custom URI schemes (`myapp://`) have no OS-level ownership
verification.** Any app can register the same scheme. iOS Universal
Links and Android App Links fix this by requiring a cryptographically
verified JSON file served at a well-known path on your domain — but
only if the file is served correctly.

**Source:**
- https://developer.apple.com/documentation/xcode/supporting-universal-links-in-your-app
- https://developer.android.com/training/app-links/verify-android-applinks

## The attack: custom URI scheme hijacking

```
1. Legitimate app registers   example project://oauth/callback
2. Attacker app registers     example project://oauth/callback  (same scheme)
3. OAuth server redirects to  example project://oauth/callback?code=AUTH_CODE
4. OS shows app picker (or silently picks attacker on some Android versions)
5. Attacker app receives the authorization code
6. Attacker exchanges code for tokens using their own client_secret (if PKCE not enforced)
```

**Impact:** Full account takeover if PKCE is not enforced.

## Mitigation 1 — PKCE (mandatory for mobile OAuth)

PKCE (RFC 7636) makes the authorization code useless without the
`code_verifier`. Even if an attacker receives the code, they cannot
exchange it.

```typescript
// Mobile client (React Native / Swift / Kotlin) — generate PKCE
function generateCodeVerifier(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoded = new TextEncoder().encode(verifier);
  const hash = await crypto.subtle.digest("SHA-256", encoded);
  return btoa(String.fromCharCode(...new Uint8Array(hash)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

// Authorization URL must include:
// &code_challenge=<challenge>&code_challenge_method=S256

// Token exchange must include:
// &code_verifier=<original_verifier>
```

On the server (Worker), reject token exchanges that lack a verifier:
```typescript
if (!body.code_verifier) {
  return Response.json({ error: "invalid_request", error_description: "code_verifier required" }, { status: 400 });
}
```

## Mitigation 2 — Use Universal Links / App Links (not custom schemes)

Replace `example project://oauth/callback` with
`https://example.com/oauth/callback`. The OS routes `https://` links
to the registered app only when the domain verification JSON is valid.

### iOS: Apple App Site Association (AASA)

Must be served at exactly: `https://example.com/.well-known/apple-app-site-association`

Requirements:
- Content-Type: `application/json`
- No redirect
- Must be served over HTTPS
- Must not require authentication

```json
{
  "applinks": {
    "apps": [],
    "details": [
      {
        "appID": "TEAMID.com.orchords.example project",
        "paths": ["/oauth/callback*", "/invite/*"]
      }
    ]
  }
}
```

### Android: Digital Asset Links

Must be served at: `https://example.com/.well-known/assetlinks.json`

```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "com.orchords.example project",
    "sha256_cert_fingerprints": [
      "AA:BB:CC:..."
    ]
  }
}]
```

Get the fingerprint:
```bash
keytool -list -v -keystore release.keystore -alias mykey | grep SHA256
```

## Cloudflare Worker serving /.well-known/

Serve the verification files from a Worker so they are always
fresh, correctly Content-Typed, and globally fast.

```typescript
// In your routing Worker (wrangler.toml routes = ["example.com/*"])
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/.well-known/apple-app-site-association") {
      // Must NOT redirect. Must be application/json.
      const aasa = {
        applinks: {
          apps: [],
          details: [
            {
              appID: "TEAMID.com.orchords.example project",
              paths: ["/oauth/callback*", "/invite/*"],
            },
          ],
        },
      };
      return new Response(JSON.stringify(aasa), {
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "public, max-age=3600",
        },
      });
    }

    if (url.pathname === "/.well-known/assetlinks.json") {
      const assetLinks = [
        {
          relation: ["delegate_permission/common.handle_all_urls"],
          target: {
            namespace: "android_app",
            package_name: "com.orchords.example project",
            sha256_cert_fingerprints: [env.ANDROID_SHA256_FINGERPRINT],
          },
        },
      ];
      return new Response(JSON.stringify(assetLinks), {
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "public, max-age=3600",
        },
      });
    }

    return handleApp(request, env);
  },
};
```

Store the fingerprint as a secret: `wrangler secret put ANDROID_SHA256_FINGERPRINT`

## Common verification failures

| Failure | Cause | Fix |
|---|---|---|
| iOS falls back to Safari | Wrong Content-Type or redirect | Serve as `application/json`, no redirect |
| Android verification pending | Cache not invalidated after first deploy | Wait 20 min; clear app data |
| iOS doesn't open app | App not installed or wrong Team ID | Verify Team ID in Apple Developer portal |
| `aasa-validator` returns error | `paths` array missing or wrong format | Use `paths` not `path`; prefix `/` required |

Validate iOS file: https://branch.io/resources/aasa-validator/
Validate Android file: https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://example.com&relation=delegate_permission/common.handle_all_urls

## Redirect URI allowlisting on the OAuth server

Only accept `https://example.com/oauth/callback` as a valid redirect
URI. Reject custom schemes and wildcard paths.

```typescript
const ALLOWED_REDIRECT_URIS = new Set([
  "https://example.com/oauth/callback",
  "https://example.com/oauth/callback/native", // for native app deeplink
]);

function validateRedirectUri(uri: string): boolean {
  return ALLOWED_REDIRECT_URIS.has(uri);
}
```

## Verification
- iOS: Install app; tap `https://example.com/invite/test` link in Notes → should open app
- iOS: Uninstall app; tap same link → should open Safari (not App Store)
- Android: `adb shell pm verify-app-links --re-verify com.orchords.example project`
- Run `curl -I https://example.com/.well-known/apple-app-site-association` → Content-Type must be `application/json`, status 200 (not 301/302)
- Attempt OAuth with a custom scheme redirect URI → server must reject

## Gotchas
- **The "CDN redirect" gotcha.** Cloudflare's "Always Use HTTPS"
  redirect will intercept `http://` requests for the AASA file.
  Apple's CDN fetches the file over HTTPS directly, so this is fine —
  but ensure no Cloudflare Page Rule redirects the `/.well-known/`
  path.
- **The "app not installed" gotcha.** On iOS, if the app is not
  installed, Universal Links fall through to Safari. The OAuth code
  in the URL is now visible in browser history. Always use short-lived
  codes (< 60 s) and PKCE.
- **The "appID format" gotcha.** The `appID` in AASA must be
  `<TEAM_ID>.<BUNDLE_ID>`, not just the bundle ID.
- **The "Android verification delay" gotcha.** Android verifies App
  Links asynchronously after install. There is a ~20 min window where
  links open in the browser. Production builds must use
  `autoVerify: true` in the intent filter.

## Related
- `security/oauth-best-practices.md`
- `security/the session management guidance in security/`
- `cloudflare/workers-best-practices.md`
- `cloudflare/cors-pages-functions.md`
- Apple Universal Links: https://developer.apple.com/documentation/xcode/supporting-universal-links-in-your-app
- Android App Links: https://developer.android.com/training/app-links/verify-android-applinks
- RFC 7636 PKCE: https://www.rfc-editor.org/rfc/rfc7636
- OAuth 2.0 for Native Apps (RFC 8252): https://www.rfc-editor.org/rfc/rfc8252
