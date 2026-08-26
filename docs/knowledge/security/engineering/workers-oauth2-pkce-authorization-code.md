# OAuth2 Authorization Code + PKCE Flow in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to implement a server-side OAuth2 Authorization Code flow with PKCE inside a Cloudflare Worker without a persistent process to hold session state. Because Workers are stateless and edge-distributed, the authorization state (`code_verifier`, `state`) must survive the redirect round-trip in KV. This pattern covers the full flow: generating the PKCE challenge, redirecting to the provider, handling the callback, exchanging the code, and issuing HttpOnly session cookies with refresh token rotation.

---

## Context
PKCE (Proof Key for Code Exchange, RFC 7636) prevents authorization code interception attacks by binding the code exchange to a verifier that only the initiating client knows. In a Worker context, the `code_verifier` is generated at `/oauth/authorize`, stored in KV with a 10-minute TTL keyed by an opaque `state` value, then retrieved at `/oauth/callback` to complete the exchange. Refresh token rotation invalidates the old token on every use, limiting the blast radius of a leaked refresh token.

---

## Section 1 — KV Binding & Wrangler Config

```toml
# wrangler.toml
name = "oauth-worker"
main = "src/index.ts"
compatibility_date = "2025-04-01"

[[kv_namespaces]]
binding = "OAUTH_STATE"
id = "<your-kv-namespace-id>"
preview_id = "<your-preview-id>"

[vars]
OAUTH_CLIENT_ID      = "<client_id>"
OAUTH_REDIRECT_URI   = "https://app.example.com/oauth/callback"
OAUTH_AUTHORIZE_URL  = "https://accounts.example.com/oauth/authorize"
OAUTH_TOKEN_URL      = "https://accounts.example.com/oauth/token"
OAUTH_SCOPES         = "openid profile email"
COOKIE_DOMAIN        = "app.example.com"
```

```toml
# Keep OAUTH_CLIENT_SECRET in a secret, not vars:
# npx wrangler secret put OAUTH_CLIENT_SECRET
```

---

## Section 2 — Implementation

```typescript
// src/index.ts
export interface Env {
  OAUTH_STATE: KVNamespace;
  OAUTH_CLIENT_ID: string;
  OAUTH_CLIENT_SECRET: string;
  OAUTH_REDIRECT_URI: string;
  OAUTH_AUTHORIZE_URL: string;
  OAUTH_TOKEN_URL: string;
  OAUTH_SCOPES: string;
  COOKIE_DOMAIN: string;
}

const STATE_TTL_SECONDS = 600; // 10 minutes

function randomBase64URL(bytes: number): string {
  const arr = crypto.getRandomValues(new Uint8Array(bytes));
  return btoa(String.fromCharCode(...arr))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

async function sha256Base64URL(plain: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(plain);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

async function handleAuthorize(request: Request, env: Env): Promise<Response> {
  const codeVerifier = randomBase64URL(48);      // 64 printable chars
  const codeChallenge = await sha256Base64URL(codeVerifier); // S256
  const state = randomBase64URL(24);             // opaque CSRF token

  // Store verifier+state in KV
  await env.OAUTH_STATE.put(
    `pkce:${state}`,
    JSON.stringify({ codeVerifier }),
    { expirationTtl: STATE_TTL_SECONDS }
  );

  const params = new URLSearchParams({
    response_type: "code",
    client_id: env.OAUTH_CLIENT_ID,
    redirect_uri: env.OAUTH_REDIRECT_URI,
    scope: env.OAUTH_SCOPES,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
  });

  return Response.redirect(`${env.OAUTH_AUTHORIZE_URL}?${params}`, 302);
}

interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  token_type: string;
  id_token?: string;
}

async function handleCallback(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const error = url.searchParams.get("error");

  if (error) {
    return new Response(`OAuth error: ${error}`, { status: 400 });
  }
  if (!code || !state) {
    return new Response("Missing code or state", { status: 400 });
  }

  // Retrieve and delete the PKCE state (one-time use)
  const kvKey = `pkce:${state}`;
  const stored = await env.OAUTH_STATE.get(kvKey);
  if (!stored) {
    return new Response("Invalid or expired state", { status: 400 });
  }
  await env.OAUTH_STATE.delete(kvKey);

  const { codeVerifier } = JSON.parse(stored) as { codeVerifier: string };

  // Exchange code for tokens
  const tokenRes = await fetch(env.OAUTH_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: env.OAUTH_REDIRECT_URI,
      client_id: env.OAUTH_CLIENT_ID,
      client_secret: env.OAUTH_CLIENT_SECRET,
      code_verifier: codeVerifier,
    }),
  });

  if (!tokenRes.ok) {
    const body = await tokenRes.text();
    return new Response(`Token exchange failed: ${body}`, { status: 502 });
  }

  const tokens: TokenResponse = await tokenRes.json();

  // Issue HttpOnly, Secure, SameSite=Lax session cookie
  const sessionId = randomBase64URL(32);
  const cookieMaxAge = tokens.expires_in ?? 3600;

  // In production: store tokens in KV/D1 keyed by sessionId
  // Here we encode in cookie for brevity (sign in production!)
  const cookieValue = btoa(JSON.stringify({
    access_token: <redacted-secret>
    refresh_token: tokens.refresh_token,
    expires_at: Date.now() + cookieMaxAge * 1000,
  }));

  const cookieHeader = [
    `session=${cookieValue}`,
    `Max-Age=${cookieMaxAge}`,
    `Domain=${env.COOKIE_DOMAIN}`,
    "Path=/",
    "HttpOnly",
    "Secure",
    "SameSite=Lax",
  ].join("; ");

  return new Response(null, {
    status: 302,
    headers: {
      Location: "/",
      "Set-Cookie": cookieHeader,
    },
  });
}

async function handleRefresh(request: Request, env: Env): Promise<Response> {
  const cookie = request.headers.get("cookie") ?? "";
  const match = cookie.match(/session=([^;]+)/);
  if (!match) return new Response("No session", { status: 401 });

  let session: { access_token: string; refresh_token?: string; expires_at: number };
  try {
    session = JSON.parse(atob(match[1]));
  } catch {
    return new Response("Invalid session", { status: 401 });
  }

  if (!session.refresh_token) {
    return new Response("No refresh token", { status: 401 });
  }

  const tokenRes = await fetch(env.OAUTH_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: session.refresh_token,
      client_id: env.OAUTH_CLIENT_ID,
      client_secret: env.OAUTH_CLIENT_SECRET,
    }),
  });

  if (!tokenRes.ok) return new Response("Refresh failed", { status: 401 });

  const tokens: TokenResponse = await tokenRes.json();
  // Rotate: use new refresh_token if provided, else keep old one
  const newRefresh = tokens.refresh_token ?? session.refresh_token;

  const newCookieValue = btoa(JSON.stringify({
    access_token: <redacted-secret>
    refresh_token: newRefresh,
    expires_at: Date.now() + (tokens.expires_in ?? 3600) * 1000,
  }));

  return new Response(JSON.stringify({ ok: true }), {
    headers: {
      "Content-Type": "application/json",
      "Set-Cookie": [
        `session=${newCookieValue}`,
        `Max-Age=${tokens.expires_in ?? 3600}`,
        `Domain=${env.COOKIE_DOMAIN}`,
        "Path=/",
        "HttpOnly",
        "Secure",
        "SameSite=Lax",
      ].join("; "),
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/oauth/authorize") return handleAuthorize(request, env);
    if (url.pathname === "/oauth/callback") return handleCallback(request, env);
    if (url.pathname === "/oauth/refresh") return handleRefresh(request, env);
    return new Response("Not found", { status: 404 });
  },
};
```

---

## Section 3 — Integration / Testing

```typescript
// test/oauth.test.ts
import { describe, it, expect } from "vitest";

describe("PKCE helpers", () => {
  it("code_challenge is BASE64URL(SHA-256(verifier))", async () => {
    const verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    // Expected from RFC 7636 Appendix B
    const expected = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";
    const encoder = new TextEncoder();
    const data = encoder.encode(verifier);
    const digest = await crypto.subtle.digest("SHA-256", data);
    const actual = btoa(String.fromCharCode(...new Uint8Array(digest)))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=/g, "");
    expect(actual).toBe(expected);
  });
});
```

```bash
# Simulate the full flow with curl (replace with real provider values)
# Step 1: get authorization URL
curl -v "https://oauth-worker.example.workers.dev/oauth/authorize"
# Follow redirect to provider, log in, get redirected back to /oauth/callback?code=...&state=...

# Step 2: inspect KV to confirm state was deleted after callback
npx wrangler kv key list --namespace-id=<id> --prefix="pkce:"
# Should return empty list after successful callback

# Step 3: check session cookie in browser DevTools > Application > Cookies
```

---

## Anti-patterns
- **Storing `code_verifier` in the session cookie** — The cookie is sent back to the provider redirect; a MITM who intercepts the redirect request gets both the code and the verifier. Store in KV instead.
- **Not deleting state from KV after callback** — Leaves the door open to replay attacks where an attacker reuses the same authorization code and state.
- **Using `plain` code challenge method** — `S256` is required by RFC 7636 for public clients; `plain` provides no protection against code interception.
- **Encoding tokens directly in a cookie without signing** — The example above is for illustration; in production, sign the cookie with HMAC or use a server-side session store.

---

## Gotchas
- `btoa`/`atob` in Workers handle Latin-1 only; for unicode strings, encode to UTF-8 bytes first via `TextEncoder`.
- Some OAuth providers enforce exact redirect URI matching including trailing slashes; ensure `OAUTH_REDIRECT_URI` in wrangler.toml matches the registered value byte-for-byte.
- KV TTL is eventually consistent across edge nodes; in rare cases a callback arriving at a different PoP within milliseconds of the authorize request may not see the state. Use a slightly longer TTL (10+ minutes) to accommodate.
- Refresh token rotation means the old token is immediately invalid. If the client retries on network error, the second retry will fail. Implement idempotency at the application layer.

---

## Verification
```bash
# Deploy
npx wrangler deploy

# Confirm state TTL in KV
npx wrangler kv key list --namespace-id=<id> --prefix="pkce:"

# After callback, key should be gone
npx wrangler kv key get --namespace-id=<id> "pkce:<state>"
# Expected: null / not found

# Check cookie attributes in response headers
curl -sI "https://oauth-worker.example.workers.dev/oauth/callback?code=test&state=test" \
  | grep -i set-cookie
```

---

## Related
- `workers-api-key-management-kv-hashed.md`
- `workers-csp-report-endpoint-d1.md`

---

## Sources
- RFC 7636 — Proof Key for Code Exchange — https://datatracker.ietf.org/doc/html/rfc7636
- RFC 6749 — The OAuth 2.0 Authorization Framework — https://datatracker.ietf.org/doc/html/rfc6749
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/api/
- OWASP OAuth Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
