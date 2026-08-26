# GitHub Actions OIDC Token Exchange via a Cloudflare Workers Token Broker

2026-08-24 / example.com / production

---

## Symptom / Use-case

Your organization runs multiple GitHub Actions workflows that all need short-lived Cloudflare API
tokens. Rather than configuring each repository with OIDC federation independently, a central
Cloudflare Worker acts as the token broker: it validates the inbound GitHub OIDC JWT, enforces
claim-based policy, and issues a scoped Cloudflare API token via the Cloudflare Token API. All
consuming workflows exchange one HTTP request for a ready-to-use token.

## Context

GitHub Actions provides an OIDC JWT at `$ACTIONS_ID_TOKEN_REQUEST_URL` with sub, repository,
ref, environment, and other claims signed by GitHub's keys. Cloudflare's OIDC federation
(`cloudflare-token-exchange`) lets you map those claims to token permissions automatically, but
setting up the trust relationship per-account is required. A Workers token broker centralises
policy: one Worker handles all exchange requests, validates the JWT offline using cached JWKS,
enforces org/repo allow-lists, and calls Cloudflare's `POST /user/tokens` endpoint to mint a
narrow token on behalf of the caller.

```
┌─────────────────┐   1. getIDToken()    ┌──────────────────────────────┐
│  GitHub Actions │ ──────────────────►  │  GitHub OIDC endpoint        │
│  workflow job   │ ◄──────────────────  │  (JWT with iss, sub, repo...) │
└─────────────────┘   2. JWT             └──────────────────────────────┘
        │
        │  3. POST /exchange  { jwt }
        ▼
┌─────────────────────────────────────────┐
│  Cloudflare Worker – token broker       │
│  • verify JWT signature (cached JWKS)   │
│  • enforce org/repo/env allow-list      │
│  • call CF Tokens API to mint token     │
└─────────────────────────────────────────┘
        │
        │  4. { token, expires_at }
        ▼
┌─────────────────┐
│  GitHub Actions │ 5. CLOUDFLARE_API_TOKEN=<token>
│  wrangler deploy│    wrangler deploy --env production
└─────────────────┘
```

## Code

### Workers token broker — JWKS verification and claim enforcement

```typescript
// workers/token-broker/src/index.ts
import { Env } from "./types";

const GITHUB_JWKS_URL = "https://token.actions.githubusercontent.com/.well-known/jwks";
const GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/exchange") {
      return new Response("Not Found", { status: 404 });
    }

    const { jwt } = (await request.json()) as { jwt: string };
    if (!jwt) return new Response("Missing jwt", { status: 400 });

    // Verify signature using JWKS cached in KV
    const payload = await verifyGitHubJWT(jwt, env);
    if (!payload) return new Response("Invalid token", { status: 401 });

    // Enforce allow-list: only repos in the org may use this broker
    const allowed = (env.ALLOWED_REPOS ?? "").split(",");
    if (!allowed.includes(payload.repository)) {
      return new Response("Repository not allowed", { status: 403 });
    }

    // Mint a scoped Cloudflare API token
    const cfToken = await mintCloudflareToken(payload, env);
    return Response.json({ token: cfToken.value, expires_at: cfToken.expires_on });
  },
};

async function verifyGitHubJWT(jwt: string, env: Env): Promise<Record<string, string> | null> {
  const [headerB64, payloadB64, sigB64] = jwt.split(".");
  const header = JSON.parse(atob(headerB64));

  // Fetch or cache JWKS
  let jwksRaw = await env.KV.get("github_jwks");
  if (!jwksRaw) {
    const res = await fetch(GITHUB_JWKS_URL);
    jwksRaw = await res.text();
    await env.KV.put("github_jwks", jwksRaw, { expirationTtl: 3600 });
  }

  const { keys } = JSON.parse(jwksRaw);
  const key = keys.find((k: { kid: string }) => k.kid === header.kid);
  if (!key) return null;

  const cryptoKey = await crypto.subtle.importKey(
    "jwk",
    key,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );

  const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const sig = Uint8Array.from(atob(sigB64.replace(/-/g, "+").replace(/_/g, "/")), (c) =>
    c.charCodeAt(0),
  );

  const valid = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", cryptoKey, sig, data);
  if (!valid) return null;

  const payload = JSON.parse(atob(payloadB64));
  if (payload.iss !== GITHUB_OIDC_ISSUER) return null;
  if (payload.exp < Math.floor(Date.now() / 1000)) return null;

  return payload;
}

async function mintCloudflareToken(
  claims: Record<string, string>,
  env: Env,
): Promise<{ value: string; expires_on: string }> {
  const expiresAt = new Date(Date.now() + 15 * 60 * 1000).toISOString(); // 15 min
  const body = {
    name: `ci-${claims.repository.replace("/", "-")}-${Date.now()}`,
    policies: [
      {
        effect: "allow",
        resources: { [`com.cloudflare.api.account.${env.CF_ACCOUNT_ID}`]: "*" },
        permission_groups: [{ id: env.WORKERS_DEPLOY_PERMISSION_GROUP_ID }],
      },
    ],
    not_before: new Date().toISOString(),
    expires_on: expiresAt,
  };

  const res = await fetch("https://api.cloudflare.com/client/v4/user/tokens", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_ADMIN_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  const { result } = (await res.json()) as { result: { value: string; expires_on: string } };
  return result;
}
```

### Wrangler configuration for the broker Worker

```toml
# workers/token-broker/wrangler.toml
name = "oidc-token-broker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "KV"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
CF_ACCOUNT_ID = "YOUR_CF_ACCOUNT_ID"
WORKERS_DEPLOY_PERMISSION_GROUP_ID = "WORKERS_SCRIPTS_EDIT_GROUP_ID"
ALLOWED_REPOS = "myorg/api,myorg/frontend"

# CF_ADMIN_TOKEN is a secret: wrangler secret put CF_ADMIN_TOKEN
```

### GitHub Actions workflow — consuming the broker

```yaml
# .github/workflows/deploy.yml
name: Deploy via Token Broker

on:
  push:
    branches: [main]

permissions:
  id-token: write  # Required to call getIDToken()
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Obtain OIDC JWT
        id: oidc
        run: |
          OIDC_TOKEN=$(curl -sSfL \
            -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=https://token-broker.myorg.workers.dev" \
            | jq -r '.value')
          echo "::add-mask::$OIDC_TOKEN"
          echo "token=$OIDC_TOKEN" >> "$GITHUB_OUTPUT"

      - name: Exchange for Cloudflare API token
        id: exchange
        run: |
          RESPONSE=$(curl -sSf \
            -X POST https://token-broker.myorg.workers.dev/exchange \
            -H "Content-Type: application/json" \
            -d "{\"jwt\": \"${{ steps.oidc.outputs.token }}\"}")
          CF_TOKEN=$(echo "$RESPONSE" | jq -r '.token')
          echo "::add-mask::$CF_TOKEN"
          echo "cf_token=$CF_TOKEN" >> "$GITHUB_OUTPUT"

      - name: Deploy with Wrangler
        env:
          CLOUDFLARE_API_TOKEN: ${{ steps.exchange.outputs.cf_token }}
        run: npx wrangler deploy --env production
```

### Token broker unit test (Vitest + Miniflare)

```typescript
// workers/token-broker/src/index.test.ts
import { describe, it, expect, beforeAll } from "vitest";
import { unstable_dev } from "wrangler";

describe("token broker", () => {
  let worker: Awaited<ReturnType<typeof unstable_dev>>;

  beforeAll(async () => {
    worker = await unstable_dev("src/index.ts", { experimental: { disableExperimentalWarning: true } });
  });

  afterAll(async () => await worker.stop());

  it("rejects requests without a jwt", async () => {
    const res = await worker.fetch("/exchange", {
      method: "POST",
      body: JSON.stringify({}),
      headers: { "Content-Type": "application/json" },
    });
    expect(res.status).toBe(400);
  });

  it("rejects forged JWTs", async () => {
    const res = await worker.fetch("/exchange", {
      method: "POST",
      body: JSON.stringify({ jwt: "eyJhbGciOiJSUzI1NiJ9.e30.invalidsig" }),
      headers: { "Content-Type": "application/json" },
    });
    expect(res.status).toBe(401);
  });
});
```

### Rotate the admin token without downtime

```shell
# 1. Mint a new admin token in Cloudflare dashboard with identical permissions
NEW_TOKEN="<new-token>"

# 2. Push the new secret — Wrangler propagates it across all Worker instances
wrangler secret put CF_ADMIN_TOKEN --name oidc-token-broker <<< "$NEW_TOKEN"

# 3. Revoke the old token in the CF dashboard after confirming the Worker responds OK
curl -sSf https://token-broker.myorg.workers.dev/health
```

## Anti-patterns

- **Storing a long-lived Cloudflare API token in GitHub Secrets as a fallback.** This defeats the
  secretless goal. If the broker is unavailable, fail the workflow explicitly.
- **Skipping the `exp` claim check.** A GitHub OIDC JWT expires in 10 minutes; not validating
  expiry allows replay attacks within that window.
- **Caching the broker response token across workflow runs.** Each run must exchange a fresh JWT;
  tokens minted by `mintCloudflareToken` are already scoped to 15 minutes.
- **Using a wildcard resource `"*": "*"` in the minted token policy.** Scope to the specific
  account or zone identifier that the workflow actually needs.

## Gotchas

- `ACTIONS_ID_TOKEN_REQUEST_URL` is only populated when `permissions.id-token: write` is set at
  the job or workflow level. Without it, the variable is empty and curl fails silently unless you
  check the exit code.
- The JWKS cache TTL in KV should be at most one hour. GitHub rotates keys infrequently but does
  so without notice; a zero-TTL fetch on cache miss handles key-rollover transparently.
- Cloudflare API Tokens created via the API do not appear in the dashboard under the service
  account that owns `CF_ADMIN_TOKEN`; they appear under the user who owns the admin token. Budget
  for token count limits (~500 active tokens per user).
- The `audience` claim in the OIDC JWT must match the value passed to `?audience=` in the
  `$ACTIONS_ID_TOKEN_REQUEST_URL` query string. Mismatches cause verification failures that look
  like signature errors.

## Verification

```shell
# Manually request a JWT from GitHub Actions (run inside a job):
TOKEN=$(curl -sSfL \
  -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
  "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=https://token-broker.myorg.workers.dev" \
  | jq -r '.value')

# Exchange it:
curl -sSf -X POST https://token-broker.myorg.workers.dev/exchange \
  -H "Content-Type: application/json" \
  -d "{\"jwt\": \"$TOKEN\"}" | jq .

# Confirm the minted token works:
curl -sSf -H "Authorization: Bearer <minted-token>" \
  "https://api.cloudflare.com/client/v4/user/tokens/verify" | jq .result.status
```

## Related

- `github-actions-oidc-cloudflare-deploy.md`
- `github-actions-oidc-multi-cloud-federation-workers.md`
- `github-apps-jwt-webcrypto-workers-auth.md`
- `github-app-installation-token-workers-api-client.md`

## Sources

- <https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect>
- <https://developers.cloudflare.com/fundamentals/api/reference/permissions/>
- <https://developers.cloudflare.com/workers/runtime-apis/web-crypto/>
- <https://token.actions.githubusercontent.com/.well-known/openid-configuration>
