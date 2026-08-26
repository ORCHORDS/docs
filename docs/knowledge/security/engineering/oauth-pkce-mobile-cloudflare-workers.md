# oauth-pkce-mobile-cloudflare-workers

**Issue:** OAuth 2.0 PKCE flow breaks on mobile when deep link
redirect URIs are misrouted, state parameter is lost between
app backgrounding, and Workers KV token storage is not rotated
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented — example project project (mobile, Workers KV)

## Symptom

iOS users completing the 21+ age verification OAuth redirect
land back in the app with `error=invalid_grant`. Android users
sporadically receive `error=state_mismatch`. On both platforms,
the token exchange fails when the app has been backgrounded
for more than 30 seconds between the authorization request
and the redirect return.

## Context

example project uses an OAuth 2.0 authorization code + PKCE flow to
complete age verification via a third-party identity provider.
The Cloudflare Worker acts as the confidential token endpoint
(holds the client secret). The React Native app initiates PKCE
and receives the authorization code via a deep link redirect.
Workers KV stores issued refresh tokens and state nonces.

## PKCE flow overview for mobile

```
App                    Worker               Identity Provider
 |                       |                        |
 |--generate verifier --> (stored in SecureStore)  |
 |--compute challenge --> |                        |
 |--open browser -------> |                        |
 |                        |                        |
 |                        |<-- auth request -------|
 |                        |    (challenge, state)   |
 |<-- deep link callback --|<-- code + state -------|
 |    example project://callback      |                        |
 |--POST /api/auth/token-> |                        |
 |    code + verifier      |--POST token exchange-->|
 |                         |    code + secret + verifier
 |<-- access + refresh ----|<-- tokens ------------|
```

The Worker is the only party that holds `CLIENT_SECRET`. The
mobile app never sees it. PKCE protects the code in transit.

## Deep link redirect handling

Custom URI schemes (`example project://`) are not registered at the OS
level until the app is installed. Use Universal Links (iOS) or
App Links (Android) instead — they fall back to the web if the
app is not installed and are not interceptable by other apps.

```json
// iOS — apple-app-site-association
// hosted at https://example project.app/.well-known/apple-app-site-association
{
  "applinks": {
    "apps": [],
    "details": [
      {
        "appID": "TEAMID.com.orchords.example project",
        "paths": ["/api/auth/callback"]
      }
    ]
  }
}
```

```json
// Android — assetlinks.json
// hosted at https://example project.app/.well-known/assetlinks.json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "com.orchords.example project",
    "sha256_cert_fingerprints": ["AA:BB:CC:..."]
  }
}]
```

Serve these from the Next.js static export via the `/public`
directory or a Cloudflare Pages `_redirects` passthrough to a
Worker that returns the JSON.

## State parameter storage on mobile

The `state` nonce must survive app backgrounding. On iOS, apps
can be fully evicted from memory during the external browser
redirect. `sessionStorage` and in-memory state do not survive.

```ts
// Correct: persist state to SecureStore before browser open
import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";
import { openAuthSessionAsync } from "expo-web-browser";

export async function startOAuthFlow(): Promise<void> {
  // 1. Generate PKCE verifier
  const verifier = await Crypto.getRandomBytesAsync(64)
    .then((b) => btoa(String.fromCharCode(...b))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, ""));

  // 2. Compute S256 challenge
  const digest = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    verifier,
    { encoding: Crypto.CryptoEncoding.BASE64 }
  );
  const challenge = digest
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");

  // 3. State nonce
  const state = await Crypto.getRandomBytesAsync(16)
    .then((b) => btoa(String.fromCharCode(...b)));

  // 4. Persist before leaving app — survives backgrounding
  await SecureStore.setItemAsync("pkce_verifier", verifier);
  await SecureStore.setItemAsync("oauth_state", state);

  const url = new URL("https://idp.example.com/authorize");
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", CLIENT_ID);
  url.searchParams.set("redirect_uri", REDIRECT_URI);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("state", state);
  url.searchParams.set("scope", "openid age_verify");

  await openAuthSessionAsync(url.toString(), REDIRECT_URI);
}
```

## State validation and token exchange in the Worker

```ts
// Worker — POST /api/auth/token
export async function handleTokenExchange(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{
    code: string;
    verifier: string;
    state: string;
    expected_state: string;
  }>();

  // Validate state — use timing-safe comparison
  if (!timingSafeEqual(body.state, body.expected_state)) {
    return new Response("state_mismatch", { status: 400 });
  }

  // Exchange code at IdP — Worker holds client_secret
  const tokenRes = await fetch("https://idp.example.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code: body.code,
      redirect_uri: REDIRECT_URI,
      client_id: env.OAUTH_CLIENT_ID,
      client_secret: env.OAUTH_CLIENT_SECRET, // secret stays here
      code_verifier: body.verifier,
    }),
  });
  if (!tokenRes.ok) {
    return new Response("invalid_grant", { status: 400 });
  }

  const { access_token, refresh_token, id_token } =
    await tokenRes.json<OAuthTokenResponse>();

  // Store refresh token in KV with jti as key
  const jti = crypto.randomUUID();
  await env.KV.put(
    `oauth_refresh:${jti}`,
    JSON.stringify({ refresh_token, issued_at: Date.now() }),
    { expirationTtl: 60 * 60 * 24 * 30 } // 30 days
  );

  // Issue internal example project JWT — do not return IdP tokens
  const waspJwt = await signJwt(
    { sub: extractSub(id_token), jti, age_verified: true },
    env.JWT_SECRET,
    900
  );

  return Response.json({ access_token: waspJwt, jti });
}
```

## Token rotation in Workers KV

Workers KV is eventually consistent (up to 60s). Use it for
refresh tokens, not for real-time revocation. For immediate
revocation (account ban, age reverification), pair KV with a
D1 lookup on the critical path.

```
KV key schema:
  oauth_refresh:{jti}  → { refresh_token, issued_at, user_id }
  oauth_revoked:{jti}  → "1"  (TTL = original token lifetime)

Rotation:
  1. Client sends jti to POST /api/auth/refresh
  2. Worker reads oauth_refresh:{jti} from KV
  3. Worker checks oauth_revoked:{jti} — reject if present
  4. Worker exchanges refresh_token at IdP
  5. Worker writes NEW jti to KV, sets TTL
  6. Worker writes oauth_revoked:{old_jti} with short TTL
  7. Worker returns new example project JWT + new jti to client
```

## Anti-patterns

- Using a custom URI scheme (`example project://`) as the redirect URI —
  any app can register the same scheme on Android; use App Links.
- Storing the PKCE verifier in React Native's `useState` or
  module-level variable — evicted on app backgrounding.
- Sending the IdP `refresh_token` directly to the mobile client
  — the Worker should proxy it and issue an internal token pair.
- Reusing the same `state` value across multiple authorization
  requests — state must be per-request random nonce.
- Setting Workers KV TTL to the same value as the access token
  (15 min) for the refresh token entry — KV storage is cheap;
  set TTL to the full 30-day refresh token lifetime.

## Gotchas

- `expo-web-browser` on iOS uses `ASWebAuthenticationSession`
  which shares cookies with Safari. If the IdP has an active
  session cookie, it may skip the age verification step and
  return an ID token without a fresh identity check. The example project
  Worker should validate `auth_time` in the IdP id_token.
- Android App Links require the SHA-256 cert fingerprint of the
  signing certificate in `assetlinks.json`. Debug and release
  builds have different certs; maintain both fingerprints in the
  `assetlinks.json` served from Pages during development.
- Workers KV `get` returns `null` for keys that have expired or
  never existed — treat both as invalid refresh token. Do not
  distinguish between "expired" and "never issued" in the error
  response to the client.
- The `code` from an authorization code flow is single-use and
  short-lived (typically 60–120 s at the IdP). Mobile deep link
  delivery can take several seconds on a cold launch. Measure
  the round-trip and alert if median exceeds 30 s.

## Verification

- Simulate app eviction between auth request and callback:
  force-quit app on iOS after opening the browser, reopen via
  universal link → flow should succeed using persisted verifier
- Replay a used code to the Worker's token endpoint →
  Worker must return `invalid_grant`
- Submit a wrong `state` value → Worker returns `state_mismatch`
- Confirm IdP `refresh_token` is never present in Worker
  response body — only internal example project JWT
- Check KV entries via `wrangler kv key list` after a login;
  confirm TTLs are set

## Related

- `security/jwt-storage-mobile-workers-auth.md`
- `security/oauth-pkce-flow.md`
- `security/api-key-rotation-workers-kv-secrets.md`
- `cloudflare/workers-kv-consistency-model.md`
- `mobile/expo-universal-links-setup.md`

## Sources

- https://www.rfc-editor.org/rfc/rfc7636 (PKCE)
- https://developers.cloudflare.com/kv/api/
- https://developer.apple.com/documentation/xcode/supporting-associated-domains
- https://developer.android.com/training/app-links/verify-android-applinks
- https://docs.expo.dev/versions/latest/sdk/web-browser/
