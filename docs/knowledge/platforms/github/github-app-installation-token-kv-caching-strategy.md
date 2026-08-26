# GitHub App Installation Token Caching in Cloudflare Workers KV

2026-08-24 / example.com / production

---

## Symptom / Use-case

A Cloudflare Worker calls GitHub API on behalf of an installed GitHub App — posting check runs,
reading repository contents, creating deployments. Without caching, every request generates a
new installation token via `POST /app/installations/{id}/access_tokens`. Each GitHub App is
limited to a small number of installation tokens (they expire after 1 hour) and the JWT signing
adds latency to every request. Workers KV removes both problems: tokens are cached until 5
minutes before expiry, signed JWTs are amortised across many requests, and the 60-seconds-or-less
eventual consistency of KV is acceptable for tokens that live for an hour.

## Context

A GitHub App authenticates in two stages:

1. **App JWT** — RS256 JWT signed with the App's private key, valid for 10 minutes, used only to
   call GitHub App APIs (list installations, get installation, create installation token).
2. **Installation token** — short-lived Bearer token returned by
   `POST /app/installations/{id}/access_tokens`, valid for exactly 3600 seconds.

Workers cannot use the Node.js `jsonwebtoken` library; JWTs must be signed with
`crypto.subtle.sign` (WebCrypto). Both the App JWT and the installation token benefit from
caching in KV. The App JWT can be re-used for up to ~9 minutes (leave 1 minute headroom); the
installation token for up to ~55 minutes (leave 5 minutes headroom).

```
Worker request
    │
    ├─ KV.get("installation_token:{installationId}")
    │      hit  ──────────────────────────────────────► return cached token
    │      miss ▼
    ├─ KV.get("app_jwt")
    │      hit  ──► sign skip ─────────────────────────► use cached JWT
    │      miss ──► sign new App JWT via SubtleCrypto
    │                └─► KV.put("app_jwt", jwt, {expirationTtl: 540})
    │
    ├─ POST /app/installations/{id}/access_tokens
    │
    └─ KV.put("installation_token:{id}", token, {expirationTtl: 3300})
           └────────────────────────────────────────────► return fresh token
```

## Code

### KV-backed token cache helper

```typescript
// src/github/token-cache.ts
export interface Env {
  KV: KVNamespace;
  GH_APP_ID: string;
  GH_APP_PRIVATE_KEY: string; // PEM — store as secret
}

const APP_JWT_TTL_SECONDS = 540;        // 9 min (token lives 10 min)
const INSTALLATION_TOKEN_TTL = 3300;    // 55 min (token lives 60 min)

export async function getInstallationToken(
  installationId: number,
  env: Env,
): Promise<string> {
  const kvKey = `installation_token:${installationId}`;

  // Fast path: cached token still valid
  const cached = await env.KV.get(kvKey);
  if (cached) return cached;

  // Obtain App JWT (cached separately)
  const appJwt = await getAppJwt(env);

  // Exchange for installation token
  const res = await fetch(
    `https://api.github.com/app/installations/${installationId}/access_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${appJwt}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "orchords-worker/1.0",
      },
    },
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub installation token request failed ${res.status}: ${body}`);
  }

  const { token } = (await res.json()) as { token: string };

  // Cache with TTL; KV expirationTtl is in seconds
  await env.KV.put(kvKey, token, { expirationTtl: INSTALLATION_TOKEN_TTL });

  return token;
}

async function getAppJwt(env: Env): Promise<string> {
  const cached = await env.KV.get("app_jwt");
  if (cached) return cached;

  const jwt = await signAppJwt(env.GH_APP_ID, env.GH_APP_PRIVATE_KEY);
  await env.KV.put("app_jwt", jwt, { expirationTtl: APP_JWT_TTL_SECONDS });
  return jwt;
}
```

### WebCrypto RS256 App JWT signing

```typescript
// src/github/jwt.ts
export async function signAppJwt(appId: string, pemKey: string): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const payload = { iat: now - 60, exp: now + 600, iss: appId };

  const encode = (obj: object) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

  const headerB64 = encode(header);
  const payloadB64 = encode(payload);
  const message = new TextEncoder().encode(`${headerB64}.${payloadB64}`);

  // Import PEM key (Workers supports PKCS#8 DER; convert from PEM first)
  const pem = pemKey.replace(/-----[^-]+-----/g, "").replace(/\s/g, "");
  const der = Uint8Array.from(atob(pem), (c) => c.charCodeAt(0));

  const cryptoKey = await crypto.subtle.importKey(
    "pkcs8",
    der,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );

  const signature = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", cryptoKey, message);
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(signature)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

  return `${headerB64}.${payloadB64}.${sigB64}`;
}
```

### Worker entry-point using the cached token

```typescript
// src/index.ts
import { getInstallationToken } from "./github/token-cache";
import type { Env } from "./github/token-cache";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const installationId = Number(env.GH_INSTALLATION_ID);

    const token = await getInstallationToken(installationId, env);

    // Example: list repository check runs
    const res = await fetch(
      "https://api.github.com/repos/myorg/myrepo/check-runs",
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "orchords-worker/1.0",
        },
      },
    );

    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

### Wrangler and KV configuration

```toml
# wrangler.toml
name = "github-app-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "KV"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
GH_APP_ID = "123456"
GH_INSTALLATION_ID = "78901234"

# Secrets (never in vars):
# wrangler secret put GH_APP_PRIVATE_KEY
```

### Cache invalidation — force-evict a stale token

```shell
# If GitHub revokes the installation token early (e.g. after App re-installation),
# evict it manually from KV so the Worker fetches a fresh one on next request.

NAMESPACE_ID="YOUR_KV_NAMESPACE_ID"
INSTALLATION_ID="78901234"
ACCOUNT_ID="YOUR_CF_ACCOUNT_ID"

curl -sSf -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${NAMESPACE_ID}/values/installation_token:${INSTALLATION_ID}" \
  -H "Authorization: Bearer $CF_API_TOKEN"

# Also evict the App JWT if the private key was rotated:
curl -sSf -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${NAMESPACE_ID}/values/app_jwt" \
  -H "Authorization: Bearer $CF_API_TOKEN"
```

## Anti-patterns

- **Using a single KV key for all installations.** Each installation ID must have its own KV key;
  tokens from different installations carry different repository and permission scopes.
- **Setting `expirationTtl` to the full 3600 seconds.** Tokens expire server-side at exactly
  3600 s; a Worker that retrieves a nearly-expired token from KV will fail GitHub API calls mid-
  flight. Always leave at least 5 minutes of headroom.
- **Storing the private key in `[vars]`.** Wrangler vars appear in `wrangler.toml` and may be
  committed to git. Store the PEM key as a secret via `wrangler secret put`.
- **Sharing the same installation token across Worker isolates with no KV.** Without KV, each
  cold-started isolate calls `access_tokens` independently, burning rate limit quota quickly
  under traffic.

## Gotchas

- KV reads in Workers are served from the nearest PoP and have eventual consistency across PoPs
  (up to ~60 seconds lag). In practice, you may see a burst of `access_tokens` calls when a
  token is first written. This is safe — GitHub returns a new valid token each time; the last
  KV write wins.
- The private key PEM includes newlines. When storing as a Worker secret via `wrangler secret
  put`, pipe the multi-line file directly: `wrangler secret put GH_APP_PRIVATE_KEY < key.pem`.
  If you interpolate it as an env variable shell may strip newlines causing PEM parse failures.
- GitHub App JWTs have a maximum lifetime of 10 minutes. Do not increase the `exp` claim
  beyond `now + 600`; GitHub will reject the JWT.
- `crypto.subtle.importKey` with `"pkcs8"` requires the key in PKCS#8 DER format. GitHub App
  private keys are generated as PKCS#1 PEM. Convert with
  `openssl pkcs8 -topk8 -nocrypt -in private-key.pem -out private-key-pkcs8.pem` before storing.

## Verification

```shell
# Confirm a fresh token is cached after the first Worker request
NAMESPACE_ID="YOUR_KV_NAMESPACE_ID"
ACCOUNT_ID="YOUR_CF_ACCOUNT_ID"

curl -sSf \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${NAMESPACE_ID}/values/installation_token:78901234" \
  -H "Authorization: Bearer $CF_API_TOKEN" | head -c 30

# Validate the cached installation token against GitHub
CACHED_TOKEN=$(curl -sSf \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${NAMESPACE_ID}/values/installation_token:78901234" \
  -H "Authorization: Bearer $CF_API_TOKEN")

curl -sSf \
  -H "Authorization: Bearer $CACHED_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/installation/repositories | jq '.total_count'
```

## Related

- `github-apps-installation-token-workers-api-client.md`
- `github-apps-jwt-webcrypto-workers-auth.md`
- `github-apps-vs-pat.md`
- `github-actions-oidc-workers-token-broker.md`

## Sources

- <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app>
- <https://developers.cloudflare.com/kv/api/write-key-value-pairs/>
- <https://developers.cloudflare.com/workers/runtime-apis/web-crypto/>
- <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app>
