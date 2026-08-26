# mobile-auth-oauth-pkce

**Issue:** Implementing OAuth 2.0 with PKCE for secure mobile authentication
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Mobile apps cannot keep a client secret confidential (the binary is reversible). OAuth 2.0 with PKCE (Proof Key for Code Exchange) is the correct flow for public clients — no client secret needed.

## Pattern / Solution
**PKCE flow:**
1. Generate random `code_verifier` (43–128 chars, base64url)
2. Hash it: `code_challenge = BASE64URL(SHA256(code_verifier))`
3. Open authorization URL in system browser (not WebView)
4. Handle redirect back to app with `code`
5. Exchange `code` + `code_verifier` for tokens

**React Native with expo-auth-session:**
```ts
import * as AuthSession from 'expo-auth-session';
import * as Crypto from 'expo-crypto';

const discovery = await AuthSession.fetchDiscoveryAsync('https://accounts.example.com');

const request = new AuthSession.AuthRequest({
  clientId: 'my-mobile-client',
  scopes: ['openid', 'profile', 'email', 'offline_access'],
  redirectUri: AuthSession.makeRedirectUri({ scheme: 'myapp' }),
  usePKCE: true, // expo-auth-session handles code_verifier internally
});

const result = await request.promptAsync(discovery);

if (result.type === 'success') {
  const { accessToken, refreshToken } = await AuthSession.exchangeCodeAsync(
    {
      clientId: 'my-mobile-client',
      code: result.params.code,
      redirectUri: request.redirectUri,
      codeVerifier: request.codeVerifier!,
    },
    discovery
  );
  // Store tokens securely
  await SecureStore.setItemAsync('access_token', accessToken);
}
```

**Token refresh:**
```ts
const tokens = await AuthSession.refreshAsync(
  { clientId: 'my-mobile-client', refreshToken },
  discovery
);
```

## Gotchas
- Never use an embedded WebView for OAuth — it allows the app to inspect credentials; always use the system browser (ASWebAuthenticationSession on iOS, Custom Tabs on Android)
- `expo-auth-session` uses an intermediate redirect via `auth.expo.io` in Expo Go; production builds must use your own scheme
- Refresh tokens are long-lived — store them with `requireAuthentication: true` in SecureStore
- `offline_access` scope is required to receive a refresh token with most providers
- Access tokens should be short-lived (15 min); never extend their lifetime just to avoid refresh logic
- Detect token expiry before the request (check `exp` in JWT) rather than on 401 response to avoid a bad UX flash

## Related
- `react-native-secure-storage.md`
- `mobile-jwt-storage-pitfalls.md`
- `react-native-biometric-auth.md`
