# GitHub Apps – Installation Token API Client in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You are building a Cloudflare Worker that calls the GitHub API on behalf of a GitHub App
installation — to read repository contents, post check runs, update deployment statuses,
or manage issues. Using a Personal Access Token (PAT) is not viable for multi-tenant
systems or production automation. You need a typed client factory that handles JWT
generation with WebCrypto, exchanges for an installation token, caches the token inside
the Worker's request lifetime (or in KV for cross-invocation reuse), and retries on 401
with a fresh token without leaking private key material.

## Context

GitHub Apps authenticate in two steps: (1) sign a JWT with the App's RSA private key
(10-minute maximum lifetime), then (2) POST to
`/app/installations/{installation_id}/access_tokens` to receive an installation token
valid for up to 60 minutes. Workers cannot use `crypto.subtle` with PEM-encoded keys
directly — the key must be imported as a `CryptoKey` in PKCS#8 DER format. The pattern
below derives all crypto inside the Worker using the WebCrypto API, stores the token in
KV with a TTL slightly shorter than the GitHub expiry, and exposes a simple
`githubFetch(path, init)` surface to callers.

## 1. Env Interface and Wrangler Binding

```toml
# wrangler.toml
name = "github-app-worker"
compatibility_date = "2026-06-01"

[[kv_namespaces]]
binding = "GH_TOKEN_CACHE"
id = "your-kv-namespace-id"

[vars]
GH_APP_ID = "123456"
GH_INSTALLATION_ID = "78901234"
```

```typescript
// src/types.ts
export interface Env {
  GH_TOKEN_CACHE: KVNamespace;
  GH_APP_ID: string;
  GH_INSTALLATION_ID: string;
  // Loaded as a Workers secret: wrangler secret put GH_PRIVATE_KEY_PKCS8_B64
  GH_PRIVATE_KEY_PKCS8_B64: string;
}
```

Store the private key as base64-encoded PKCS#8 DER (not PEM). Convert once:

```bash
# Strip PEM headers and base64-encode the DER bytes
openssl pkcs8 -topk8 -nocrypt -in private-key.pem -outform DER \
  | base64 -w0 \
  | wrangler secret put GH_PRIVATE_KEY_PKCS8_B64
```

## 2. JWT Generation with WebCrypto

```typescript
// src/github-jwt.ts
function base64UrlEncode(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

function encodePayload(obj: Record<string, unknown>): string {
  return base64UrlEncode(new TextEncoder().encode(JSON.stringify(obj)));
}

export async function generateAppJWT(
  appId: string,
  pkcs8Base64: string
): Promise<string> {
  const pkcs8Bytes = Uint8Array.from(atob(pkcs8Base64), (c) => c.charCodeAt(0));

  const key = await crypto.subtle.importKey(
    "pkcs8",
    pkcs8Bytes,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const now = Math.floor(Date.now() / 1000);
  const header = base64UrlEncode(
    new TextEncoder().encode(JSON.stringify({ alg: "RS256", typ: "JWT" }))
  );
  const payload = encodePayload({
    iat: now - 60,   // 60-second back-date to tolerate clock skew
    exp: now + 540,  // 9 minutes (GitHub max is 10)
    iss: appId,
  });

  const message = `${header}.${payload}`;
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(message)
  );

  return `${message}.${base64UrlEncode(signature)}`;
}
```

## 3. Installation Token Exchange with KV Cache

```typescript
// src/github-token.ts
import type { Env } from "./types.ts";
import { generateAppJWT } from "./github-jwt.ts";

const CACHE_KEY_PREFIX = "gh_install_token:";
// Cache 5 minutes short of the GitHub-reported expiry to avoid using a stale token
const EARLY_EXPIRY_SECONDS = 300;

interface InstallationTokenResponse {
  token: string;
  expires_at: string;
  permissions: Record<string, string>;
  repository_selection: "all" | "selected";
}

export async function getInstallationToken(env: Env): Promise<string> {
  const cacheKey = `${CACHE_KEY_PREFIX}${env.GH_INSTALLATION_ID}`;

  // Check KV cache first
  const cached = await env.GH_TOKEN_CACHE.get(cacheKey);
  if (cached) return cached;

  const jwt = await generateAppJWT(env.GH_APP_ID, env.GH_PRIVATE_KEY_PKCS8_B64);

  const response = await fetch(
    `https://api.github.com/app/installations/${env.GH_INSTALLATION_ID}/access_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": `my-github-app/${env.GH_APP_ID}`,
      },
    }
  );

  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `GitHub token exchange failed: ${response.status} ${response.statusText} — ${body}`
    );
  }

  const data = (await response.json()) as InstallationTokenResponse;
  const expiresAt = new Date(data.expires_at).getTime() / 1000;
  const now = Math.floor(Date.now() / 1000);
  const ttl = Math.max(60, expiresAt - now - EARLY_EXPIRY_SECONDS);

  await env.GH_TOKEN_CACHE.put(cacheKey, data.token, {
    expirationTtl: Math.floor(ttl),
  });

  return data.token;
}
```

## 4. Typed API Client Factory

```typescript
// src/github-client.ts
import type { Env } from "./types.ts";
import { getInstallationToken } from "./github-token.ts";

const GITHUB_API = "https://api.github.com";

export interface GitHubClient {
  get<T>(path: string, init?: RequestInit): Promise<T>;
  post<T>(path: string, body: unknown, init?: RequestInit): Promise<T>;
  patch<T>(path: string, body: unknown, init?: RequestInit): Promise<T>;
}

async function githubRequest<T>(
  env: Env,
  method: string,
  path: string,
  body?: unknown,
  init: RequestInit = {},
  retried = false
): Promise<T> {
  const token = await getInstallationToken(env);

  const response = await fetch(`${GITHUB_API}${path}`, {
    ...init,
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": `my-github-app/${env.GH_APP_ID}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  // Evict stale cached token and retry once on 401
  if (response.status === 401 && !retried) {
    const cacheKey = `gh_install_token:${env.GH_INSTALLATION_ID}`;
    await env.GH_TOKEN_CACHE.delete(cacheKey);
    return githubRequest<T>(env, method, path, body, init, true);
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`GitHub API ${method} ${path} → ${response.status}: ${text}`);
  }

  // 204 No Content (e.g. DELETE endpoints)
  if (response.status === 204) return undefined as T;

  return response.json() as Promise<T>;
}

export function createGitHubClient(env: Env): GitHubClient {
  return {
    get: <T>(path: string, init?: RequestInit) =>
      githubRequest<T>(env, "GET", path, undefined, init),
    post: <T>(path: string, body: unknown, init?: RequestInit) =>
      githubRequest<T>(env, "POST", path, body, init),
    patch: <T>(path: string, body: unknown, init?: RequestInit) =>
      githubRequest<T>(env, "PATCH", path, body, init),
  };
}
```

## 5. Usage in a Worker Handler

```typescript
// src/index.ts
import type { Env } from "./types.ts";
import { createGitHubClient } from "./github-client.ts";

interface RepoInfo {
  full_name: string;
  default_branch: string;
  visibility: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const owner = url.searchParams.get("owner");
    const repo = url.searchParams.get("repo");
    if (!owner || !repo) {
      return Response.json({ error: "owner and repo are required" }, { status: 400 });
    }

    const gh = createGitHubClient(env);

    const repoInfo = await gh.get<RepoInfo>(`/repos/${owner}/${repo}`);

    // Post a deployment status on behalf of the App
    await gh.post(`/repos/${owner}/${repo}/deployments`, {
      ref: repoInfo.default_branch,
      environment: "production",
      auto_merge: false,
      required_contexts: [],
      description: "Triggered by Workers API client",
    });

    return Response.json({ repository: repoInfo.full_name });
  },
};
```

## Anti-patterns

- **Storing the raw PEM string as a secret.** `crypto.subtle.importKey` does not accept
  PEM; you must strip headers and DER-encode before storing. Attempting to parse PEM
  inside the Worker each invocation is fragile and slow.
- **Creating a new `CryptoKey` import on every request.** Import the key once per
  Worker isolate lifecycle using a module-level `let` initialized lazily, not inside
  the fetch handler, to avoid redundant `importKey` calls.
- **Using a single global JWT for multiple requests.** JWTs expire in 9 minutes. Cache
  installation tokens (which last 60 minutes) in KV — do not cache the JWT.
- **Not setting `User-Agent`.** GitHub API rejects requests without it; Workers default
  `User-Agent` is not a valid GitHub API identifier.

## Gotchas

- The `iat` must be backdated by at least 60 seconds to survive GitHub's clock skew
  check. JWTs with `iat` in the future are rejected with 401.
- KV's `expirationTtl` minimum is 60 seconds. If the token has fewer than 65 seconds
  remaining after subtracting `EARLY_EXPIRY_SECONDS`, clamp TTL to 60.
- Installation tokens are scoped to the permissions granted at install time. If your App
  is installed with `read-only` on contents, the client will receive 403 on write paths
  regardless of token freshness.
- The `delete` KV call in the retry path is a best-effort eviction. Under concurrent
  requests, two Workers may simultaneously exchange a new token; KV's last-writer-wins
  semantics make this safe but wasteful.

## Verification

```bash
# Confirm PKCS8 conversion is correct before storing
openssl pkcs8 -topk8 -nocrypt -in private-key.pem -outform DER \
  | openssl rsa -inform DER -noout -text 2>/dev/null \
  | head -5

# Test JWT locally with wrangler dev
wrangler dev --env local

# Inspect KV cache entries
wrangler kv key list --namespace-id <your-kv-id> --prefix gh_install_token:
```

## Related

- `github-apps-jwt-webcrypto-workers-auth.md`
- `github-apps-installation-tokens.md`
- `github-apps-vs-pat.md`
- `github-apps-private-key-rotation-ci.md`
- `github-app-webhook-workers-handler.md`

## Sources

- GitHub Docs – Authenticating as a GitHub App installation: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation
- WebCrypto API – SubtleCrypto.importKey: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/importKey
- Cloudflare Workers KV – expirationTtl: https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
- GitHub API versioning: https://docs.github.com/en/rest/overview/api-versions
