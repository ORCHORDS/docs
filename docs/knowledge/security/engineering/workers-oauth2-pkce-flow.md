# OAuth2 PKCE Flow Implementation in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker needs to act as an OAuth2 client — redirecting users to an authorization server, handling the callback, exchanging the authorization code for tokens, and managing token lifecycle — all without a server-side session store. Using the Proof Key for Code Exchange (PKCE) extension eliminates the need for a client secret in public clients and protects against authorization code interception attacks.

---

## Context

Traditional OAuth2 flows rely on a client secret to authenticate the token exchange. In edge environments the client secret would be embedded in Worker code, making it retrievable via source inspection. PKCE replaces the client secret with a per-request cryptographic challenge derived from a random `code_verifier`. The `code_verifier` is generated in the browser (or by the Worker on behalf of the user), hashed to produce a `code_challenge` sent in the authorization request, and then the raw verifier is sent at token exchange time so the authorization server can verify it.

KV stores the per-request PKCE state, the resulting tokens are encrypted before storage, and the refresh token rotation pattern ensures compromised refresh tokens are invalidated on first use.

---

## Solution

```typescript
// oauth2-pkce.ts
// Complete OAuth2 PKCE flow for Cloudflare Workers.

export interface OAuthConfig {
  clientId: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  revocationEndpoint?: string;
  redirectUri: string;
  scopes: string[];
  /** AES-GCM key (base64) used to encrypt tokens at rest in KV */
  encryptionKeyB64: string;
}

interface PKCEState {
  codeVerifier: string;
  state: string;
  createdAt: number;
  redirectAfter?: string;
}

interface TokenSet {
  accessToken: string;
  refreshToken?: string;
  expiresAt: number; // unix ms
  scope: string;
}

// ── PKCE helpers ─────────────────────────────────────────────────────────────

/** Generate a cryptographically random code_verifier (RFC 7636 §4.1). */
export function generateCodeVerifier(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return base64UrlEncode(bytes);
}

/** Derive the code_challenge from a verifier using S256 method. */
export async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoded = new TextEncoder().encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', encoded);
  return base64UrlEncode(new Uint8Array(digest));
}

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// ── AES-GCM encryption for KV storage ────────────────────────────────────────

async function importEncryptionKey(b64: string): Promise<CryptoKey> {
  const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  return crypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
}

async function encryptToken(plaintext: string, keyB64: string): Promise<string> {
  const key = await importEncryptionKey(keyB64);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = new TextEncoder().encode(plaintext);
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, data);
  const combined = new Uint8Array(iv.byteLength + ciphertext.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(ciphertext), iv.byteLength);
  return btoa(String.fromCharCode(...combined));
}

async function decryptToken(b64Ciphertext: string, keyB64: string): Promise<string> {
  const key = await importEncryptionKey(keyB64);
  const combined = Uint8Array.from(atob(b64Ciphertext), c => c.charCodeAt(0));
  const iv = combined.slice(0, 12);
  const ciphertext = combined.slice(12);
  const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);
  return new TextDecoder().decode(plaintext);
}

// ── Authorization redirect ────────────────────────────────────────────────────

export async function buildAuthorizationRedirect(
  config: OAuthConfig,
  kv: KVNamespace,
  redirectAfter?: string
): Promise<Response> {
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);
  const state = base64UrlEncode(crypto.getRandomValues(new Uint8Array(16)));

  const pkceState: PKCEState = {
    codeVerifier,
    state,
    createdAt: Date.now(),
    redirectAfter,
  };

  // Store PKCE state for 10 minutes — long enough for user to complete login.
  await kv.put(`pkce:${state}`, JSON.stringify(pkceState), { expirationTtl: 600 });

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    scope: config.scopes.join(' '),
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });

  return Response.redirect(`${config.authorizationEndpoint}?${params}`, 302);
}

// ── Callback handler ──────────────────────────────────────────────────────────

export async function handleOAuthCallback(
  request: Request,
  config: OAuthConfig,
  kv: KVNamespace
): Promise<Response> {
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const stateParam = url.searchParams.get('state');
  const errorParam = url.searchParams.get('error');

  if (errorParam) {
    return new Response(
      JSON.stringify({ error: 'authorization_error', detail: errorParam }),
      { status: 400, headers: { 'content-type': 'application/json' } }
    );
  }

  if (!code || !stateParam) {
    return new Response(JSON.stringify({ error: 'missing_params' }), { status: 400 });
  }

  // Retrieve and validate PKCE state.
  const stateJson = await kv.get(`pkce:${stateParam}`);
  if (!stateJson) {
    return new Response(JSON.stringify({ error: 'invalid_state' }), { status: 400 });
  }

  const pkceState: PKCEState = JSON.parse(stateJson);

  // Verify state matches (CSRF protection).
  if (pkceState.state !== stateParam) {
    return new Response(JSON.stringify({ error: 'state_mismatch' }), { status: 400 });
  }

  // One-time use: delete state immediately.
  await kv.delete(`pkce:${stateParam}`);

  // Exchange code for tokens.
  const tokenSet = await exchangeCodeForTokens(code, pkceState.codeVerifier, config);

  // Encrypt and store tokens.
  const sessionId = base64UrlEncode(crypto.getRandomValues(new Uint8Array(24)));
  const encrypted = await encryptToken(JSON.stringify(tokenSet), config.encryptionKeyB64);
  await kv.put(`session:${sessionId}`, encrypted, {
    expirationTtl: Math.floor((tokenSet.expiresAt - Date.now()) / 1000) + 300,
  });

  const redirectTarget = pkceState.redirectAfter ?? '/';
  return new Response(null, {
    status: 302,
    headers: {
      location: redirectTarget,
      'set-cookie': `sid=${sessionId}; HttpOnly; Secure; SameSite=Lax; Path=/`,
    },
  });
}

// ── Token exchange ────────────────────────────────────────────────────────────

async function exchangeCodeForTokens(
  code: string,
  codeVerifier: string,
  config: OAuthConfig
): Promise<TokenSet> {
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    code,
    code_verifier: codeVerifier,
  });

  const res = await fetch(config.tokenEndpoint, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Token exchange failed: ${res.status} ${text}`);
  }

  const json = await res.json<{
    access_token: string;
    refresh_token?: string;
    expires_in: number;
    scope: string;
  }>();

  return {
    accessToken: <redacted-secret>
    refreshToken: json.refresh_token,
    expiresAt: Date.now() + json.expires_in * 1000,
    scope: json.scope,
  };
}

// ── Refresh token rotation ────────────────────────────────────────────────────

export async function refreshAccessToken(
  sessionId: string,
  config: OAuthConfig,
  kv: KVNamespace
): Promise<TokenSet | null> {
  const encrypted = await kv.get(`session:${sessionId}`);
  if (!encrypted) return null;

  const tokenSet: TokenSet = JSON.parse(await decryptToken(encrypted, config.encryptionKeyB64));

  if (!tokenSet.refreshToken) return null;

  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    client_id: config.clientId,
    refresh_token: tokenSet.refreshToken,
  });

  const res = await fetch(config.tokenEndpoint, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!res.ok) {
    // Refresh failed — session is invalid.
    await kv.delete(`session:${sessionId}`);
    return null;
  }

  const json = await res.json<{
    access_token: string;
    refresh_token?: string;
    expires_in: number;
    scope: string;
  }>();

  const newTokenSet: TokenSet = {
    accessToken: <redacted-secret>
    // Use new refresh token if provided (rotation), otherwise keep existing.
    refreshToken: json.refresh_token ?? tokenSet.refreshToken,
    expiresAt: Date.now() + json.expires_in * 1000,
    scope: json.scope,
  };

  const newEncrypted = await encryptToken(JSON.stringify(newTokenSet), config.encryptionKeyB64);
  await kv.put(`session:${sessionId}`, newEncrypted, {
    expirationTtl: json.expires_in + 300,
  });

  return newTokenSet;
}

// ── Logout with token revocation ─────────────────────────────────────────────

export async function logout(
  sessionId: string,
  config: OAuthConfig,
  kv: KVNamespace
): Promise<Response> {
  const encrypted = await kv.get(`session:${sessionId}`);

  if (encrypted && config.revocationEndpoint) {
    const tokenSet: TokenSet = JSON.parse(await decryptToken(encrypted, config.encryptionKeyB64));

    const revokeToken = async (token: string, hint: string) => {
      const body = new URLSearchParams({
        token,
        token_type_hint: hint,
        client_id: config.clientId,
      });
      await fetch(config.revocationEndpoint!, {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
      });
    };

    await revokeToken(tokenSet.accessToken, 'access_token');
    if (tokenSet.refreshToken) {
      await revokeToken(tokenSet.refreshToken, 'refresh_token');
    }
  }

  await kv.delete(`session:${sessionId}`);

  return new Response(null, {
    status: 302,
    headers: {
      location: '/',
      'set-cookie': 'sid=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0',
    },
  });
}
```

---

## Implementation Details

- `generateCodeVerifier` produces 32 random bytes base64url-encoded, yielding a 43-character string that satisfies RFC 7636 length requirements (43–128 characters).
- `generateCodeChallenge` uses `SubtleCrypto.digest('SHA-256')` — the only PKCE method (`S256`) that all modern authorization servers accept.
- PKCE state is stored in KV with a 10-minute TTL; the key is deleted immediately after the callback is processed to enforce one-time use.
- Tokens are encrypted with AES-GCM (256-bit key, random 96-bit IV prepended to ciphertext) before being written to KV — never stored as plaintext.
- Refresh token rotation stores the new refresh token returned by the authorization server; if none is returned, the existing one is reused (some servers issue rolling tokens, others do not rotate).
- Session cookies are `HttpOnly; Secure; SameSite=Lax` — they cannot be read by client-side JavaScript and are not sent on cross-site top-level navigations.

---

## Anti-patterns

- Do not skip PKCE even if the authorization server does not require it — it is mandatory for public clients (RFC 9700).
- Do not store the `code_verifier` in a cookie — it must be on the server side to prevent client extraction.
- Do not use `plain` as the `code_challenge_method`; always use `S256`.
- Do not persist tokens longer than their `expires_in` — the KV TTL should match the token lifetime.
- Do not skip token revocation on logout — a revoked refresh token cannot be replayed even if the session cookie is stolen.

---

## Gotchas

- The KV `expirationTtl` parameter is in seconds, not milliseconds; divide `expires_in * 1000` back to seconds.
- `Response.redirect` in Workers sends a 302 by default; ensure downstream `SameSite=Lax` cookies are respected by the browser.
- Authorization servers that do not support `token_type_hint` on revocation return 200 anyway — do not treat a non-200 revocation response as a logout failure.
- `json<T>()` is a Workers-specific `Response` method — it performs `res.json()` and casts to `T`; it is not available in standard browser `fetch`.
- Encrypted KV values roughly triple in size due to base64 encoding of the IV + ciphertext; account for this in KV size limits (25 MB per value).

---

## Verification

```bash
# 1. Deploy and open the auth start URL.
curl -v https://your-worker.example.com/auth/login
# Expected: 302 redirect to authorization server with code_challenge in query string.

# 2. After completing login, inspect the callback URL.
# Expected: 302 redirect to / with Set-Cookie: sid=...; HttpOnly; Secure

# 3. Verify session is stored in KV.
npx wrangler kv key list --binding SESSION_KV
# Expected: keys prefixed with session:

# 4. Test refresh.
curl https://your-worker.example.com/auth/refresh \
  -H 'Cookie: sid=<your-session-id>'
# Expected: 200 with updated access token.

# 5. Test logout.
curl -v https://your-worker.example.com/auth/logout \
  -H 'Cookie: sid=<your-session-id>'
# Expected: 302 / with sid cookie cleared (Max-Age=0).
```

---

## Related

- `documentation/docs/policies/security/workers-api-key-management.md`
- `documentation/docs/policies/security/workers-content-security-policy-builder.md`
- RFC 7636 — PKCE: https://datatracker.ietf.org/doc/html/rfc7636
- RFC 9700 — OAuth 2.0 Security Best Practices: https://datatracker.ietf.org/doc/html/rfc9700

---

## Sources

- Cloudflare Workers SubtleCrypto: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- Cloudflare KV: https://developers.cloudflare.com/kv/
- OAuth 2.0 for Browser-Based Applications (RFC 9449): https://datatracker.ietf.org/doc/html/rfc9449
