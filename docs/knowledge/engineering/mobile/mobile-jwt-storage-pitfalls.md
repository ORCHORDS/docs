# mobile-jwt-storage-pitfalls

**Issue:** Common mistakes when storing and using JWTs in mobile apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
JWTs are commonly used as access tokens. Storing them insecurely or not validating them correctly leads to token theft, session fixation, or accepting expired/tampered tokens.

## Pattern / Solution
**Storage decision tree:**
```
Access token (short-lived, < 15 min)
  → In-memory (JS variable / React state)
  → Lost on app restart — acceptable, use refresh token to get new one

Refresh token (long-lived)
  → expo-secure-store / iOS Keychain / Android Keystore
  → NEVER in AsyncStorage, MMKV (unencrypted), or localStorage
```

**In-memory token manager:**
```ts
let accessToken: string | null = null;

export function setAccessToken(token: string) { accessToken = token; }
export function getAccessToken() { return accessToken; }
export function clearTokens() { accessToken = null; }

// Intercept all API calls
axiosInstance.interceptors.request.use(async config => {
  if (!accessToken || isExpired(accessToken)) {
    accessToken = await refreshAccessToken();
  }
  config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});
```

**Check expiry without a library:**
```ts
function isExpired(token: string): boolean {
  const payload = JSON.parse(atob(token.split('.')[1]));
  return Date.now() / 1000 > payload.exp - 30; // 30-second buffer
}
```

**Validate on server (never trust client-side validation alone):**
- Verify signature with correct public key
- Check `iss`, `aud`, `exp`, `nbf` claims
- Maintain a token revocation list for logout

## Gotchas
- `atob` is available in React Native via Hermes but not in all versions; use `base64-js` for reliability
- Don't store access tokens in SecureStore — the latency of reading from Keychain on every request adds up; keep them in memory
- Large JWTs (> 4 KB) can exceed cookie/header limits on some servers; use opaque tokens if claims are large
- JWT `exp` is seconds since epoch, not milliseconds — a common `Date.now() > exp` bug
- Logout must revoke the refresh token on the server; clearing local storage alone is not sufficient
- Rotating refresh tokens (each use issues a new one) limits the damage from token theft

## Related
- `react-native-secure-storage.md`
- `mobile-auth-oauth-pkce.md`
- `ios-keychain-storage.md`
