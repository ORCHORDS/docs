# jwt-storage-mobile-workers-auth

**Issue:** JWT access tokens stored in the wrong location on
mobile clients lose protection or become inaccessible behind
Cloudflare Workers auth due to ITP and SameSite restrictions
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented — example project project (iOS/Android, Workers)

## Symptom

After a example project user logs in on iOS Safari (PWA mode), their
session expires silently after 7 days even though the refresh
token is set to 30 days. On Android Chrome the session persists.
On native iOS/Android apps cookies set by the Worker are missing
on subsequent requests despite `SameSite=None; Secure`.

## Context

example project is an anonymous social platform with 21+ age gate. The
Workers API issues JWTs. The client is a Next.js static export
running as a Cloudflare Pages app. Mobile users access example project
either through a browser PWA or a React Native app. Each surface
has different JWT storage constraints.

## Storage option comparison

```
+---------------------+----------+---------+----------+----------+
| Option              | XSS risk | CSRF    | ITP safe | Native   |
|                     |          | risk    |          | app OK   |
+---------------------+----------+---------+----------+----------+
| httpOnly cookie     | Low      | Medium* | No**     | No***    |
| localStorage        | High     | Low     | Yes      | Yes      |
| sessionStorage      | High     | Low     | Yes      | Yes      |
| SecureStore (RN)    | Low      | N/A     | Yes      | Yes      |
| Keychain (iOS)      | Low      | N/A     | Yes      | Yes      |
| EncryptedStorage    | Low      | N/A     | Yes      | Yes      |
+---------------------+----------+---------+----------+----------+
* Mitigated by CSRF token or SameSite=Lax
** ITP partitions cookie storage after 7 days cross-site
*** Native HTTP clients strip cookies unless explicitly handled
```

Rule: use `httpOnly` cookies for browser (PWA) sessions; use
native secure storage for React Native apps. Never share the
same JWT storage strategy across both surfaces.

## iOS Safari ITP (Intelligent Tracking Prevention)

ITP partitions first-party storage for domains that Safari
classifies as "tracking". For example project, if the Worker API lives
at `api.example project.app` and the Pages site is at `example project.app`, Safari
treats the cookie as third-party on initial load:

```
ITP rules (Safari 17+):
- Cookie set by api.example project.app read from example project.app JS → blocked
- Cookie set by example project.app (same-site request to api) → 7-day cap
- After 7 days without user interaction → purged
```

Fix: issue the JWT cookie from the same registrable domain.
Serve the Worker on `example project.app/api/*` (same-site) rather than
`api.example project.app` (cross-site). Use Cloudflare Pages Functions or
route the Worker on the same hostname:

```toml
# wrangler.toml — bind Worker to same hostname via routes
[[routes]]
pattern = "example project.app/api/*"
zone_name = "example project.app"
```

The cookie then originates from `example project.app` and avoids ITP's
cross-site classification.

## SameSite cookie behavior on mobile browsers

```
SameSite=Strict  → cookie not sent on any cross-site navigation
                   PWA link from another app → no session
SameSite=Lax    → sent on top-level GET navigation
                   safe for most PWA use cases
SameSite=None   → requires Secure; sent cross-site
                   needed only if API is on a different origin
```

For example project Pages + same-origin Worker:

```ts
// Workers response — set auth cookie
response.headers.append(
  "Set-Cookie",
  [
    `access_token=${accessToken}`,
    "HttpOnly",
    "Secure",
    "SameSite=Lax",   // correct for same-registrable-domain
    "Path=/",
    "Max-Age=900",    // 15 min access token
  ].join("; ")
);
response.headers.append(
  "Set-Cookie",
  [
    `refresh_token=${refreshToken}`,
    "HttpOnly",
    "Secure",
    "SameSite=Lax",
    "Path=/api/auth/refresh",  // scope to refresh endpoint only
    "Max-Age=2592000",         // 30 days
  ].join("; ")
);
```

## React Native secure storage

For the React Native app, never use AsyncStorage for tokens:

```ts
// BAD — AsyncStorage is unencrypted plain text
import AsyncStorage from "@react-native-async-storage/async-storage";
await AsyncStorage.setItem("access_token", jwt); // ← NEVER

// GOOD — platform native secure storage
import * as SecureStore from "expo-secure-store";

export async function storeTokens(
  access: string,
  refresh: string
): Promise<void> {
  await SecureStore.setItemAsync("example project_access_token", access, {
    keychainAccessible:
      SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
  });
  await SecureStore.setItemAsync("example project_refresh_token", refresh, {
    keychainAccessible:
      SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
  });
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync("example project_access_token");
}
```

`AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY` maps to iOS Keychain
`kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` and Android
Keystore with no backup. Tokens do not sync to iCloud or
Android Backup, which is correct for auth credentials.

## Workers token refresh middleware

```ts
// Worker middleware — silent token refresh on 401
export async function withAuth(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const accessToken = <redacted-secret> "access_token");
  if (!accessToken) return unauthorizedResponse();

  const payload = await verifyJwt(accessToken, env.JWT_SECRET);
  if (payload) return handler(request, env, ctx, payload);

  // Token expired — try refresh cookie
  const refreshToken = getCookieValue(request, "refresh_token");
  if (!refreshToken) return unauthorizedResponse();

  const stored = await env.KV.get(`refresh:${refreshToken}`);
  if (!stored) return unauthorizedResponse(); // revoked

  const user = JSON.parse(stored);
  const newAccess = await signJwt(user, env.JWT_SECRET, 900);
  const res = await handler(
    request, env, ctx, user
  );
  res.headers.append(
    "Set-Cookie",
    `access_token=${newAccess}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=900`
  );
  return res;
}
```

## Anti-patterns

- Storing JWT in `localStorage` in a PWA — any injected script
  (third-party analytics, CDN compromise) can exfiltrate it.
- Using `SameSite=None` on a same-origin API — unnecessary and
  widens the cookie's exposure surface.
- Setting `Max-Age` on the access token cookie equal to the
  refresh token lifetime — the access token should be short.
- Sharing a single `Path=/` refresh token cookie across all
  routes — scope it to the refresh endpoint to reduce exposure.
- Using the iOS Keychain `kSecAttrAccessibleAlways` attribute —
  tokens will be accessible even when device is locked or in
  an MDM backup.

## Gotchas

- iOS Safari PWA (Add to Home Screen) has a unique ITP profile.
  A site added to the home screen gets a separate cookie jar;
  cookies set in Safari are not shared with the PWA context.
  Users who switch between Safari and the PWA will lose their
  session. Issue a fresh token pair on each PWA launch.
- Android Chrome Custom Tabs share cookies with Chrome, but
  React Native's `expo-web-browser` session may not. Test token
  hand-off explicitly after an OAuth redirect.
- `SameSite=Lax` cookies are not sent on cross-site `POST`
  requests even on the same registrable domain. Age verification
  form posts must use `SameSite=None; Secure` or fetch + JSON.
- Cloudflare Workers cannot set `Domain=` on a cookie to cover
  a wildcard subdomain unless the subdomain is in the same zone.

## Verification

- iOS 17 Safari: log in, background app for 8 days, reopen →
  session should prompt refresh (ITP cap test)
- Android 14 Chrome: same flow → session should persist 30 days
- React Native iOS: `SecureStore.getItemAsync` returns token
  after device reboot (AFTER_FIRST_UNLOCK verified)
- Run `wrangler tail` during login; confirm Set-Cookie headers
  contain `HttpOnly; Secure; SameSite=Lax`
- Confirm refresh cookie `Path=/api/auth/refresh` is absent on
  non-refresh requests via browser DevTools Application tab

## Related

- `security/jwt-best-practices.md`
- `security/session-cookies-vs-jwt.md`
- `security/oauth-pkce-mobile-cloudflare-workers.md`
- `mobile/react-native-http-client-config.md`
- `cloudflare/workers-cookies-set-cookie.md`

## Sources

- https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/
- https://developers.cloudflare.com/workers/runtime-apis/headers/
- https://docs.expo.dev/versions/latest/sdk/securestore/
- https://developer.apple.com/documentation/security/keychain_services
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies#samesite_attribute
