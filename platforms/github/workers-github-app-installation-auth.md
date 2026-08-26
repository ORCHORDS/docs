# GitHub App Installation Authentication in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need a Cloudflare Worker to call GitHub APIs on behalf of a GitHub App across multiple organisations. Personal Access Tokens expire, rotate poorly, and have no scope boundary. GitHub App installation tokens are short-lived, scoped to a single installation, and can be cached and refreshed automatically inside KV.

## Context

GitHub Apps authenticate in two steps:
1. **App-level JWT** — signed with the App's RS256 private key, valid 10 minutes, used only to call the App API (`/app/installations`, `/app/installations/:id/access_tokens`).
2. **Installation token** — returned by the App API, valid 1 hour, carries the exact permissions granted by the org admin.

Cloudflare Workers cannot use Node's `crypto` module. Use the Web Crypto API (`SubtleCrypto`) instead. The private key must be stored as a Cloudflare Secret (plain PEM text).

## Solution

### Worker entrypoint and KV binding

```toml
# wrangler.toml
name = "github-app-auth"
main = "src/index.ts"
compatibility_date = "2024-11-01"

[[kv_namespaces]]
binding = "GITHUB_TOKENS"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
GITHUB_APP_ID = "123456"
```

```typescript
// src/types.ts
export interface Env {
  GITHUB_APP_PRIVATE_KEY: string; // RSA PEM, set via `wrangler secret put`
  GITHUB_APP_ID: string;
  GITHUB_TOKENS: KVNamespace;
}

export interface InstallationToken {
  token: string;
  expires_at: string; // ISO-8601
  permissions: Record<string, string>;
  repository_selection: "all" | "selected";
}
```

### JWT generation with Web Crypto (RS256)

```typescript
// src/jwt.ts
async function importRsaPrivateKey(pem: string): Promise<CryptoKey> {
  // Strip PEM headers and decode base64
  const pemContents = pem
    .replace(/<redacted-private-key>/g, "")
    .replace(/\s/g, "");
  const der = Uint8Array.from(atob(pemContents), (c) => c.charCodeAt(0));

  return crypto.subtle.importKey(
    "pkcs8",
    der.buffer,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );
}

function base64UrlEncode(bytes: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

export async function createAppJwt(appId: string, privateKeyPem: string): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const payload = {
    iat: now - 60, // issued 60 s in the past to cover clock skew
    exp: now + 9 * 60, // expires in 9 minutes
    iss: appId,
  };

  const encHeader = base64UrlEncode(new TextEncoder().encode(JSON.stringify(header)));
  const encPayload = base64UrlEncode(new TextEncoder().encode(JSON.stringify(payload)));
  const signingInput = `${encHeader}.${encPayload}`;

  const key = await importRsaPrivateKey(privateKeyPem);
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(signingInput)
  );

  return `${signingInput}.${base64UrlEncode(signature)}`;
}
```

### Installation token exchange and KV caching

```typescript
// src/auth.ts
import { createAppJwt } from "./jwt";
import type { Env, InstallationToken } from "./types";

const GITHUB_API = "https://api.github.com";
const TOKEN_TTL_SECONDS = 55 * 60; // 55 min — refresh 5 min before GitHub's 1-hour expiry

export async function getInstallationToken(
  env: Env,
  installationId: number
): Promise<string> {
  const cacheKey = `installation_token:${installationId}`;

  // 1. Try the cache first
  const cached = await env.GITHUB_TOKENS.get(cacheKey, "json") as InstallationToken | null;
  if (cached) {
    const expiresAt = new Date(cached.expires_at).getTime();
    if (expiresAt - Date.now() > 5 * 60 * 1000) {
      return cached.token; // Still has >5 min remaining
    }
  }

  // 2. Generate a fresh App JWT and request a new installation token
  const jwt = await createAppJwt(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);

  const resp = await fetch(
    `${GITHUB_API}/app/installations/${installationId}/access_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "orchords-app/1.0",
      },
    }
  );

  if (!resp.ok) {
    throw new Error(`GitHub token exchange failed: ${resp.status} ${await resp.text()}`);
  }

  const data = (await resp.json()) as InstallationToken;

  // 3. Cache in KV with explicit TTL
  await env.GITHUB_TOKENS.put(cacheKey, JSON.stringify(data), {
    expirationTtl: TOKEN_TTL_SECONDS,
  });

  return data.token;
}
```

### Scoped token with specific permissions and repositories

```typescript
// src/auth.ts (continued)
export async function getScopedInstallationToken(
  env: Env,
  installationId: number,
  options: {
    permissions?: Record<string, string>;
    repositoryIds?: number[];
  } = {}
): Promise<string> {
  const jwt = await createAppJwt(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);

  const body: Record<string, unknown> = {};
  if (options.permissions) body.permissions = options.permissions;
  if (options.repositoryIds) body.repository_ids = options.repositoryIds;

  const resp = await fetch(
    `${GITHUB_API}/app/installations/${installationId}/access_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "orchords-app/1.0",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    }
  );

  if (!resp.ok) {
    throw new Error(`Scoped token request failed: ${resp.status}`);
  }

  const data = (await resp.json()) as InstallationToken;
  return data.token;
}
```

### Multi-org support — resolving installation IDs

```typescript
// src/installations.ts
import { createAppJwt } from "./jwt";
import type { Env } from "./types";

interface Installation {
  id: number;
  account: { login: string; type: string };
}

export async function listInstallations(env: Env): Promise<Installation[]> {
  const jwt = await createAppJwt(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);
  const installations: Installation[] = [];
  let url: string | null = `${GITHUB_API}/app/installations?per_page=100`;

  while (url) {
    const resp = await fetch(url, {
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "orchords-app/1.0",
      },
    });
    const page = (await resp.json()) as Installation[];
    installations.push(...page);
    // Parse Link header for next page
    const link = resp.headers.get("Link") ?? "";
    const next = link.match(/<([^>]+)>;\s*rel="next"/);
    url = next ? next[1] : null;
  }

  return installations;
}

export async function getInstallationIdForOrg(
  env: Env,
  org: string
): Promise<number> {
  const cacheKey = `installation_id:${org}`;
  const cached = await env.GITHUB_TOKENS.get(cacheKey);
  if (cached) return parseInt(cached, 10);

  const installations = await listInstallations(env);
  const match = installations.find(
    (i) => i.account.login.toLowerCase() === org.toLowerCase()
  );
  if (!match) throw new Error(`No installation found for org: ${org}`);

  // Cache installation IDs for 24 hours
  await env.GITHUB_TOKENS.put(cacheKey, String(match.id), { expirationTtl: 86400 });
  return match.id;
}
```

### Worker entrypoint wiring it all together

```typescript
// src/index.ts
import { getInstallationIdForOrg, } from "./installations";
import { getInstallationToken } from "./auth";
import type { Env } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const org = url.searchParams.get("org");
    if (!org) return new Response("Missing ?org", { status: 400 });

    const installationId = await getInstallationIdForOrg(env, org);
    const token = await getInstallationToken(env, installationId);

    // Use the token for any GitHub API call
    const reposResp = await fetch(`https://api.github.com/installation/repositories`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "orchords-app/1.0",
      },
    });

    return new Response(await reposResp.text(), {
      status: reposResp.status,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Implementation Details

- The PEM private key from GitHub is PKCS#1. `SubtleCrypto.importKey` requires PKCS#8. Convert once at key-generation time using `openssl pkcs8 -topk8 -nocrypt -in private-key.pem -out private-key-pkcs8.pem`, then store the PKCS#8 variant as the Worker secret.
- KV `expirationTtl` is in seconds. GitHub's installation tokens last exactly 3600 s; caching at 3300 s (55 min) provides a safety margin.
- `iat` is backdated 60 seconds to account for clock drift between your Worker and GitHub's servers.
- `User-Agent` is required by GitHub API; requests without it receive `403 Forbidden`.

## Anti-patterns

- **Storing installation tokens in memory/global scope** — Worker instances are short-lived and shared; always use KV for cross-request caching.
- **Re-generating the App JWT on every API call** — JWT generation involves an RSA sign operation (slow). Cache the JWT for its remaining valid window.
- **Using a single organisation's token for cross-org calls** — Installation tokens are org-scoped. Obtain a separate token per installation.
- **Ignoring `repository_selection: "selected"`** — The token only covers explicitly approved repos; calling it against others returns 404, not 403.

## Gotchas

- The GitHub App private key downloaded from the UI is PKCS#1 RSA. `SubtleCrypto` requires PKCS#8. Failing to convert produces a cryptic `DataError: Failed to execute 'importKey'`.
- `iat` must be in the past by at least a few seconds. GitHub rejects JWTs with a future `iat`.
- KV `get` returns `null` for missing keys (not an error). Always null-check before using the cached value.
- App JWTs cannot be used to call repository APIs — only App-level endpoints. Attempting this returns `401 Requires authentication`.

## Verification

```bash
# Confirm the App JWT is valid
curl -H "Authorization: Bearer $JWT" \
     -H "Accept: application/vnd.github+json" \
     https://api.github.com/app

# Confirm the installation token works
curl -H "Authorization: Bearer $INSTALLATION_TOKEN" \
     -H "Accept: application/vnd.github+json" \
     https://api.github.com/installation/repositories
```

## Related

- `documentation/categories/github/workers-github-codeowners-enforcement.md`
- `documentation/categories/github/workers-github-metrics-analytics-engine.md`

## Sources

- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app
- https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/kv/
