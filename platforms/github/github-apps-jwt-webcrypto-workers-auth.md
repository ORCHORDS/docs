# GitHub Apps JWT Authentication with Web Crypto API in Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Worker needs to call the GitHub API as a GitHub App (not as a user or PAT). The standard Node.js
`jsonwebtoken` or `@octokit/auth-app` libraries rely on Node crypto APIs unavailable in the Workers runtime.
You need to sign an RS256 JWT using the App's private key entirely within the Web Crypto API so the Worker can
exchange it for a short-lived installation token.

## Context

GitHub Apps authenticate in two steps:
1. Sign a JWT with the App's RSA-256 private key (valid up to 10 minutes) and use it to call `/app/installations`.
2. Exchange the installation ID for an installation access token (valid 1 hour) scoped to specific repos/permissions.

The Workers runtime exposes `crypto.subtle` (Web Crypto API) which can import PKCS#8 RSA keys and produce RS256
signatures without any npm dependency. The private key is stored as a Cloudflare secret (base64-encoded DER) and
injected via `wrangler secret put`.

---

## Importing the RSA Private Key

The GitHub App private key downloaded from the GitHub UI is PEM-encoded PKCS#8. Convert it to DER and base64-encode
it for storage as a Cloudflare secret.

```bash
# One-time local conversion
openssl pkcs8 -topk8 -nocrypt -in private-key.pem -out private-key.pk8 -outform DER
base64 -w 0 private-key.pk8 | wrangler secret put GITHUB_APP_PRIVATE_KEY_B64
```

```typescript
// src/github-auth.ts
async function importAppPrivateKey(b64Der: string): Promise<CryptoKey> {
  const der = Uint8Array.from(atob(b64Der), (c) => c.charCodeAt(0));
  return crypto.subtle.importKey(
    "pkcs8",
    der.buffer,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,          // not extractable
    ["sign"],
  );
}
```

---

## Building and Signing the JWT

GitHub expects a compact JWT with `alg: RS256`. Web Crypto does not produce JWTs natively, so encode the header
and payload manually then sign the `header.payload` string.

```typescript
function b64url(input: string | Uint8Array): string {
  const bytes =
    typeof input === "string"
      ? new TextEncoder().encode(input)
      : input;
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

export async function createAppJwt(
  appId: string,
  privateKeyB64: string,
): Promise<string> {
  const key = await importAppPrivateKey(privateKeyB64);

  const now = Math.floor(Date.now() / 1_000);
  const header = b64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = b64url(
    JSON.stringify({
      iat: now - 60,   // allow 60 s clock skew
      exp: now + 540,  // 9 minutes — GitHub max is 10
      iss: appId,
    }),
  );

  const sigInput = new TextEncoder().encode(`${header}.${payload}`);
  const sigBytes = new Uint8Array(
    await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, sigInput),
  );

  return `${header}.${payload}.${b64url(sigBytes)}`;
}
```

---

## Exchanging the JWT for an Installation Token

Call `/app/installations` to find the installation ID, then POST to `/app/installations/{id}/access_tokens`.

```typescript
export interface InstallationToken {
  token: string;
  expires_at: string;
}

export async function getInstallationToken(
  appId: string,
  privateKeyB64: string,
  installationId: number,
  repositories?: string[],
): Promise<InstallationToken> {
  const jwt = await createAppJwt(appId, privateKeyB64);

  const body: Record<string, unknown> = {};
  if (repositories?.length) body.repositories = repositories;

  const res = await fetch(
    `https://api.github.com/app/installations/${installationId}/access_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "my-worker/1.0",
      },
      body: JSON.stringify(body),
    },
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`GitHub App token exchange failed ${res.status}: ${err}`);
  }

  return res.json<InstallationToken>();
}
```

---

## Caching Tokens in KV to Avoid Rate Limits

App JWT calls count against the App rate limit (5 000 req/hr for installation tokens). Cache tokens in Workers KV
with TTL set to the token's remaining lifetime minus a safety buffer.

```typescript
const TOKEN_SAFETY_BUFFER_S = 120; // refresh 2 min early

export async function getCachedInstallationToken(
  env: Env,
  installationId: number,
): Promise<string> {
  const cacheKey = `gh-install-token:${installationId}`;
  const cached = await env.CACHE_KV.get(cacheKey);
  if (cached) return cached;

  const { token, expires_at } = await getInstallationToken(
    env.GITHUB_APP_ID,
    env.GITHUB_APP_PRIVATE_KEY_B64,
    installationId,
  );

  const expiresInS =
    Math.floor((new Date(expires_at).getTime() - Date.now()) / 1_000) -
    TOKEN_SAFETY_BUFFER_S;

  if (expiresInS > 0) {
    await env.CACHE_KV.put(cacheKey, token, { expirationTtl: expiresInS });
  }

  return token;
}
```

---

## Wrangler Configuration

```toml
# wrangler.toml
name = "github-app-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "CACHE_KV"
id = "YOUR_KV_NAMESPACE_ID"

# Secrets set via wrangler secret put:
# GITHUB_APP_ID
# GITHUB_APP_PRIVATE_KEY_B64
```

---

## Anti-patterns

- **Storing the PEM directly as a secret** — PEM headers and line breaks cause base64-decode failures in
  `atob()`. Always pre-convert to raw DER and base64url-encode before storing.
- **Reusing JWTs across requests** — JWTs expire in ≤10 minutes. Build a new JWT each invocation or cache
  with an accurate TTL derived from the `exp` claim.
- **Bundling `@octokit/auth-app`** — it depends on Node's `crypto` module, which is not available in Workers
  without a polyfill shim that adds significant bundle weight. The Web Crypto path shown above has zero dependencies.
- **Missing `iat` clock-skew padding** — GitHub's servers may reject JWTs where `iat` is marginally in the
  future due to clock drift. Always subtract 60 s from the issue time.

---

## Gotchas

- `crypto.subtle.importKey` in Workers requires the key to be in **PKCS#8** format (not PKCS#1). Older GitHub App
  private key downloads may be PKCS#1 — run `openssl pkcs8 -topk8 -nocrypt` to convert.
- Installation tokens are scoped per installation. A GitHub App installed in multiple organizations requires a
  separate token call per installation ID.
- The `User-Agent` header is **required** by the GitHub API; omitting it returns HTTP 403.
- KV `expirationTtl` must be a positive integer of at least 60 seconds; values below 60 are silently clamped.

---

## Verification

```bash
# 1. Deploy and invoke the Worker
curl https://your-worker.workers.dev/github-token

# 2. Validate the returned token manually
TOKEN="<token from response>"
curl -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/vnd.github+json" \
     https://api.github.com/installation/repositories | jq '.total_count'

# 3. Confirm token expiry is within ~60 minutes
curl -H "Authorization: Bearer $TOKEN" \
     https://api.github.com/rate_limit | jq '.rate.reset'
```

---

## Related

- `github-apps-installation-tokens.md`
- `github-apps-private-key-rotation-ci.md`
- `github-app-webhook-workers-handler.md`
- `github-actions-oidc-cloudflare.md`

---

## Sources

- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/importKey
- https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app
