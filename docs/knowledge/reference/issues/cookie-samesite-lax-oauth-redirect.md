# cookie-samesite-lax-oauth-redirect

**Issue:** Session cookie is not sent on the OAuth callback redirect, causing the user to be logged out
**Date:** 2026-08-11
**Status:** documented

## Symptom
After a successful OAuth provider redirect back to `/auth/callback`, the session cookie that was set before the redirect is missing from the request. The server treats the user as unauthenticated and the login loop repeats.

## Root cause
Cookies with `SameSite=Lax` are sent on top-level cross-site navigations initiated by a link (`<a>`) or `window.location`, but the browser spec restricts them on POST-based OAuth flows and on redirects that originate from a cross-origin page. Some providers issue a POST redirect (form auto-submit) or chain multiple cross-origin hops, causing the cookie to be stripped.

## Fix
Use `SameSite=None; Secure` for the pre-auth state cookie, or store the CSRF/state value in `sessionStorage` instead of a cookie:
```ts
// Set the state cookie before redirecting to provider
response.headers.set(
  'Set-Cookie',
  `oauth_state=${state}; Path=/; HttpOnly; Secure; SameSite=None`
);
```
Validate state on callback via the cookie or sessionStorage fallback.

## Detection
In DevTools → Application → Cookies, check `SameSite` column for the state cookie before the OAuth redirect begins.

## Related
- `cors-preflight-missing-headers.md`
