# oauth-best-practices

**Issue:** OAuth 2.0 / OIDC implementation — flows, security
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a "Sign in with Google" button. You redirect to
Google. The user authenticates. Google redirects back.
You exchange the code for a token. You have the user's
email. You create an account. A week later, a security
researcher reports a CSRF vulnerability. The `state`
parameter wasn't verified.

## Root cause
**OAuth has subtle security requirements.** Each flow
has gotchas.

**Source:** IETF — OAuth 2.0:
https://datatracker.ietf.org/doc/html/rfc6749

> "OAuth 2.0 is an authorization framework ... that enables
> a third-party application to obtain limited access to an
> HTTP service."

## The 3 main OAuth flows

### Authorization Code Flow (with PKCE)
- **Use:** Web apps, mobile apps, SPAs
- **Most secure:** Server-side exchange + PKCE
- **Recommended for:** All modern apps

### Implicit Flow (deprecated)
- **Don't use.** Replaced by Authorization Code with PKCE.

### Client Credentials Flow
- **Use:** Server-to-server (no user)
- **Use case:** Service-to-service auth

For user authentication, use **Authorization Code with
PKCE**.

## The "Authorization Code + PKCE" pattern

```ts
// 1. Generate code_verifier + code_challenge
const codeVerifier = base64URLEncode(crypto.getRandomValues(new Uint8Array(32)));
const codeChallenge = await sha256(codeVerifier);

// 2. Redirect to the provider
const state = crypto.randomUUID();
const authUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
authUrl.searchParams.set('client_id', env.GOOGLE_CLIENT_ID);
authUrl.searchParams.set('redirect_uri', 'https://example.com/auth/google/callback');
authUrl.searchParams.set('response_type', 'code');
authUrl.searchParams.set('scope', 'openid email profile');
authUrl.searchParams.set('state', state);
authUrl.searchParams.set('code_challenge', codeChallenge);
authUrl.searchParams.set('code_challenge_method', 'S256');

// Store the code_verifier + state in the session
await env.SESSIONS.put(`oauth:${state}`, JSON.stringify({ codeVerifier }), {
  expirationTtl: 600,
});

return Response.redirect(authUrl.toString(), 302);

// 3. Handle the callback
async function handleCallback(code: string, state: string, env: Env) {
  // 4. Verify the state
  const stored = await env.SESSIONS.get(`oauth:${state}`);
  if (!stored) throw new Error('Invalid state');
  const { codeVerifier } = JSON.parse(stored);
  await env.SESSIONS.delete(`oauth:${state}`);

  // 5. Exchange the code for tokens
  const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      code,
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET,
      redirect_uri: 'https://example.com/auth/google/callback',
      grant_type: 'authorization_code',
      code_verifier: codeVerifier,
    }),
  });

  const tokens = await tokenResponse.json();

  // 6. Get the user info
  const userInfo = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
    headers: { 'Authorization': `Bearer ${tokens.access_token}` },
  }).then(r => r.json());

  return userInfo;
}
```

The PKCE pattern is the modern standard.

## The "state parameter" pattern

The `state` parameter is critical for CSRF protection:
```ts
// 1. Generate a random state
const state = crypto.randomUUID();

// 2. Store the state in the session (or cookie)
await env.SESSIONS.put(`oauth:${state}`, 'pending', { expirationTtl: 600 });

// 3. Send the state to the provider
authUrl.searchParams.set('state', state);

// 4. On callback, verify the state
const stored = await env.SESSIONS.get(`oauth:${state}`);
if (!stored) {
  // State wasn't generated; this is a CSRF attack
  throw new Error('Invalid state');
}
```

Without `state`, an attacker can forge a callback.

## The "PKCE" pattern

PKCE (Proof Key for Code Exchange) prevents code
interception:
```ts
// 1. Generate code_verifier (random 43-128 chars)
const codeVerifier = base64URLEncode(crypto.getRandomValues(new Uint8Array(32)));

// 2. Compute code_challenge (SHA-256 of code_verifier, base64url-encoded)
const codeChallenge = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(codeVerifier));
const codeChallengeBase64 = base64URLEncode(new Uint8Array(codeChallenge));

// 3. Send code_challenge to the provider
authUrl.searchParams.set('code_challenge', codeChallengeBase64);
authUrl.searchParams.set('code_challenge_method', 'S256');

// 4. On callback, send code_verifier
body.set('code_verifier', codeVerifier);
```

The provider verifies that the code_verifier hashes to
the code_challenge. An attacker who intercepts the code
can't exchange it.

## The "scope" choice

For each provider, choose the scopes:
- **OpenID Connect:** `openid` (required for OIDC)
- **Email:** `email` (user's email)
- **Profile:** `profile` (name, picture, etc.)
- **Custom:** provider-specific

```ts
authUrl.searchParams.set('scope', 'openid email profile');
```

Only request what you need. The user sees the scopes; a
long list is suspicious.

## The "token storage" pattern

For the access token + refresh token:
```ts
interface OAuthTokens {
  accessToken: string;
  refreshToken?: string;
  expiresAt: number;
  idToken?: string;  // OIDC: contains user info
  tokenType: 'Bearer';
  scope: string;
}

// Store encrypted in D1
await env.DB!.prepare(
  `INSERT INTO oauth_tokens (user_id, provider, access_token_hash, refresh_token_hash, expires_at)
   VALUES (?, ?, ?, ?, ?)`
).bind(
  userId,
  'google',
  await hash(tokens.accessToken),
  await hash(tokens.refreshToken),
  new Date(tokens.expiresAt * 1000).toISOString(),
).run();
```

Tokens are encrypted; the DB is the source of truth.

## The "refresh token" pattern

For a long-lived session, refresh the access token:
```ts
async function refreshAccessToken(refreshToken: string, env: Env): Promise<OAuthTokens> {
  const response = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET,
      refresh_token: refreshToken,
      grant_type: 'refresh_token',
    }),
  });

  return response.json();
}
```

The access token is short-lived; the refresh token is
long-lived.

## The "OIDC ID token" pattern

For OIDC, the ID token contains user info:
```ts
// The ID token is a JWT
const idToken = tokens.id_token;
const payload = JSON.parse(atob(idToken.split('.')[1]));

// Verify the signature
const isValid = await verifyIdToken(idToken, env);

// Get the user info
const userId = payload.sub;
const email = payload.email;
const emailVerified = payload.email_verified;
```

The ID token is signed; the signature must be verified.

## The "OIDC discovery" pattern

For OIDC, use the discovery endpoint:
```ts
const response = await fetch('https://accounts.google.com/.well-known/openid-configuration');
const config = await response.json();
// config.authorization_endpoint, config.token_endpoint, config.jwks_uri, etc.
```

The discovery endpoint provides the URLs + supported
features.

## The "client_id + client_secret" pattern

For confidential clients (server-side):
- **client_id:** Public; identifies the app
- **client_secret:** Secret; used in the token exchange

```ts
// On the server only
const response = await fetch(tokenEndpoint, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/x-www-form-urlencoded',
    'Authorization': `Basic ${btoa(`${env.GOOGLE_CLIENT_ID}:${env.GOOGLE_CLIENT_SECRET}`)}`,
  },
  body: body,
});
```

The `client_secret` is in the env, not in the client.

## The "logout" pattern

For logout, revoke the token + clear the session:
```ts
async function logout(userId: string, env: Env): Promise<void> {
  // 1. Get the refresh token
  const token = await env.DB!.prepare(
    `SELECT refresh_token_hash FROM oauth_tokens WHERE user_id = ?`
  ).bind(userId).first<{ refresh_token_hash: string }>();

  // 2. Revoke the token
  if (token) {
    await fetch(`https://oauth2.googleapis.com/revoke?token=<redacted-secret> {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  }

  // 3. Delete the session
  await env.DB!.prepare(`DELETE FROM sessions WHERE user_id = ?`).bind(userId).run();
}
```

The token is revoked; the session is cleared.

## The "OAuth vs OIDC" choice

| Use case | Use |
|---|---|
| **Authorization** (access someone else's data) | OAuth 2.0 |
| **Authentication** (verify who the user is) | OIDC (built on OAuth 2.0) |

For "Sign in with Google" → use OIDC (you get an ID token
with user info).

For "Access my Google Drive" → use OAuth 2.0 (you get an
access token).

## The "provider" choice

For OAuth providers:
- **Google:** Most popular
- **Apple:** Required for iOS apps
- **GitHub:** For developer tools
- **Microsoft:** For enterprise
- **Facebook:** For social apps
- **X (Twitter):** For social apps

Use a library (NextAuth, Auth0, Clerk) to handle the
complexity.

## The "OAuth" anti-patterns

### 1. No state parameter
- **Issue:** CSRF attack
- **Fix:** Always generate + verify state

### 2. Implicit flow
- **Issue:** Tokens in URL, no PKCE
- **Fix:** Use Authorization Code with PKCE

### 3. No PKCE
- **Issue:** Code interception
- **Fix:** Always use PKCE

### 4. Long-lived access tokens
- **Issue:** Token leakage
- **Fix:** Short access tokens + refresh tokens

### 5. client_secret in the client
- **Issue:** Secret leak
- **Fix:** Server-side only

### 6. No scope limitation
- **Issue:** Over-permission
- **Fix:** Only request what you need

## Verification
- **Test:** OAuth flow works
- **Test:** State is verified (CSRF blocked)
- **Test:** PKCE is enforced
- **Test:** Refresh token works
- **Pen test:** Annual security review

## Gotchas
- **The "no state" anti-pattern.** A CSRF vulnerability.
  Always verify state.
- **The "no PKCE" anti-pattern.** A code interception
  vulnerability. Always use PKCE.
- **The "long-lived access token" anti-pattern.** A token
  leak is a long-lived credential. Short-lived + refresh.
- **The "scope creep" anti-pattern.** Requesting too many
  scopes; users get suspicious. Only request what you
  need.
- **The "no token revocation" anti-pattern.** A user wants
  to log out; you just clear the session. The token is
  still valid. Revoke it.

## Related
- `webauthn-passkey-flow.md`
- `totp-mfa-implementation.md`
- `session-cookies-vs-jwt.md`
- `feature-cookbook-auth.md`
- `csrf-modern-defenses.md`
- IETF OAuth 2.0: https://datatracker.ietf.org/doc/html/rfc6749
- IETF PKCE: https://datatracker.ietf.org/doc/html/rfc7636
- OIDC: https://openid.net/connect/
- Auth0: https://auth0.com/docs
- NextAuth: https://next-auth.js.org/
