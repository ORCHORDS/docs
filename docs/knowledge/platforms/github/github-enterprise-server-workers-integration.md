# GitHub Enterprise Server Workers Integration

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

An organization runs GitHub Enterprise Server (GHES) on-premises or in a private cloud. The platform team wants to deploy Cloudflare Workers from GHES Actions pipelines, receive GHES webhook events in Workers, and use the GHES GraphQL/REST API from Workers-based automation. GitHub.com-centric documentation (actions/checkout@v4, OIDC, Actions marketplace) does not translate directly — endpoints, runner connectivity, OIDC issuer URLs, and Actions version compatibility differ between GHES and github.com.

## Context

GHES is a self-hosted GitHub installation with its own API base URL (`https://ghes.example.com/api/v3`), its own Actions runner coordination endpoint, and its own OIDC issuer (`https://ghes.example.com/_services/token`). Actions workflows on GHES can call out to Cloudflare's API directly when the runner has internet egress, or via an egress proxy. Workers that need to call the GHES API authenticate with installation tokens from a GitHub App installed on the GHES instance. GHES versions lag behind GitHub.com feature releases by 2–3 minor versions; always check compatibility before relying on features documented for github.com.

## GHES Actions: deploying a Cloudflare Worker

GHES Actions supports the same YAML syntax as GitHub.com Actions. The key differences are:

- Actions used in `uses:` must be synced to GHES (via `ghe-actions-sync` or `actions/runner-images`) or the workflow must use `actions/runner-images` from the GHES bundle.
- The `GITHUB_SERVER_URL` environment variable is set to the GHES hostname, not `https://github.com`.
- OIDC token exchange uses a different issuer URL — Cloudflare's Workload Identity Federation must be configured for the GHES issuer, not the GitHub.com issuer.

```yaml
# .github/workflows/deploy-worker-ghes.yml
name: Deploy Worker (GHES)

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  deploy:
    runs-on: self-hosted       # GHES typically uses self-hosted runners
    environment: production
    steps:
      - uses: actions/checkout@v4   # bundled with GHES >= 3.7

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: 22

      - name: Install dependencies
        run: npm ci

      - name: Deploy with Wrangler
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
          # GITHUB_SERVER_URL is set by GHES to https://ghes.example.com
          GHES_HOST: ${{ env.GITHUB_SERVER_URL }}
        run: |
          npx wrangler deploy --env production
```

## GHES OIDC for Cloudflare token exchange

GHES 3.8+ supports OIDC token issuance. The issuer is the GHES hostname, not `token.actions.githubusercontent.com`. Configure Cloudflare's Workload Identity Federation with the GHES issuer:

```bash
# Fetch the GHES OIDC discovery document to confirm the issuer
curl https://ghes.example.com/_services/token/.well-known/openid-configuration \
  | jq .issuer
# Output: "https://ghes.example.com/_services/token"
```

When configuring Cloudflare Workload Identity Federation, set:
- **Issuer**: `https://ghes.example.com/_services/token`
- **Subject pattern**: `repo:my-org/my-repo:environment:production`

Workflow OIDC block for GHES:

```yaml
permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: self-hosted
    environment: production
    steps:
      - name: Request GHES OIDC token
        id: oidc
        run: |
          TOKEN=$(curl --silent --fail \
            -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=cloudflare" \
            | jq -r '.value')
          echo "::add-mask::$TOKEN"
          echo "token=${TOKEN}" >> "$GITHUB_OUTPUT"

      - name: Exchange for Cloudflare API token
        id: cf-token
        env:
          CF_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
          OIDC_JWT: ${{ steps.oidc.outputs.token }}
        run: |
          CF_API_TOKEN=$(curl --silent --fail \
            -X POST \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/tokens/exchange" \
            -H "Content-Type: application/json" \
            -d "{\"oidc_token\": \"${OIDC_JWT}\"}" \
            | jq -r '.result.token')
          echo "::add-mask::$CF_API_TOKEN"
          echo "cf_token=${CF_API_TOKEN}" >> "$GITHUB_OUTPUT"

      - name: Deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ steps.cf-token.outputs.cf_token }}
        run: npx wrangler deploy --env production
```

## Calling the GHES API from a Cloudflare Worker

Workers that automate GHES workflows (e.g., reading PR data, posting check runs) must target the GHES API endpoint rather than `https://api.github.com`.

```typescript
// src/ghes-client.ts
interface GHESConfig {
  baseUrl: string;        // e.g. "https://ghes.example.com/api/v3"
  installationToken: string;
}

export class GHESClient {
  constructor(private readonly config: GHESConfig) {}

  async request<T>(path: string, options?: RequestInit): Promise<T> {
    const url = `${this.config.baseUrl}${path}`;
    const res = await fetch(url, {
      ...options,
      headers: {
        Authorization: `Bearer ${this.config.installationToken}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ghes-worker-integration/1.0",
        ...(options?.headers ?? {}),
      },
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`GHES API ${res.status} ${path}: ${body}`);
    }
    return res.json() as Promise<T>;
  }

  async getPullRequest(owner: string, repo: string, number: number) {
    return this.request<{ title: string; state: string; head: { sha: string } }>(
      `/repos/${owner}/${repo}/pulls/${number}`
    );
  }

  async createCheckRun(owner: string, repo: string, params: object) {
    return this.request(`/repos/${owner}/${repo}/check-runs`, {
      method: "POST",
      body: JSON.stringify(params),
      headers: { "Content-Type": "application/json" },
    });
  }
}
```

## Receiving GHES webhook events in a Worker

```typescript
// src/ghes-webhook-handler.ts
// GHES webhooks are signed with HMAC-SHA256, same as GitHub.com.
// The GHES admin sets the webhook secret in the Admin panel.

export async function verifyGHESWebhook(
  request: Request,
  body: string,
  secret: string
): Promise<void> {
  const sig = request.headers.get("X-Hub-Signature-256") ?? "";
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(body));
  const expected =
    "sha256=" +
    Array.from(new Uint8Array(mac))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");

  if (sig !== expected) throw new Error("Invalid GHES webhook signature");
}

export default {
  async fetch(request: Request, env: { GHES_WEBHOOK_SECRET: string }): Promise<Response> {
    const body = await request.text();
    await verifyGHESWebhook(request, body, env.GHES_WEBHOOK_SECRET);

    const event = request.headers.get("X-GitHub-Event");
    const payload = JSON.parse(body);

    if (event === "push" && payload.ref === "refs/heads/main") {
      // Trigger downstream automation (e.g. D1 migration)
      console.log(`Push to main on GHES: ${payload.repository.full_name}`);
    }

    return new Response("OK", { status: 200 });
  },
};
```

## Network considerations for self-hosted runners

GHES self-hosted runners need outbound HTTPS to `api.cloudflare.com` (Wrangler uploads) and `workers.cloudflare.com` (preview URLs). If the runner is behind a corporate proxy, set:

```yaml
      - name: Configure proxy for Wrangler
        env:
          HTTPS_PROXY: ${{ vars.CORPORATE_HTTPS_PROXY }}
          NO_PROXY: "ghes.example.com,localhost"
        run: npx wrangler deploy --env production
```

For air-gapped GHES installations, Wrangler cannot reach Cloudflare's API at all. The pattern is to build the Worker bundle on the self-hosted runner, publish the bundle as a GHES release artifact, and then have a separately networked job or an external Cloudflare Worker fetch it from the GHES API and upload it.

## Anti-patterns

- Using `https://api.github.com` as the API base URL in Workers that target a GHES installation — all requests return 404 because the repos and users do not exist on GitHub.com.
- Pinning `uses: actions/checkout@v3` in GHES workflows without checking whether v3 is bundled — GHES bundles specific versions; using an unbundled version requires internet access or manual sync.
- Assuming GitHub.com OIDC issuer URLs in Cloudflare Workload Identity Federation when the workflows run on GHES — the GHES issuer is different and the JWT will fail validation.
- Sending the GHES installation token to `https://api.github.com` — it is a GHES-internal credential and is not valid on GitHub.com.

## Gotchas

- GHES versions follow a 3-version support window. GHES 3.9 may not support OIDC or certain Actions context variables that are available on GitHub.com. Always check the GHES release notes for the installed version.
- The `GITHUB_API_URL` environment variable is set to the GHES API base URL (e.g., `https://ghes.example.com/api/v3`) in self-hosted runner jobs. Use it instead of hardcoding the GHES hostname.
- GHES webhook deliveries originate from the GHES instance's IP, not GitHub.com's IP ranges. Cloudflare WAF rules that allowlist GitHub.com IPs will block GHES webhooks.
- GitHub Apps installed on a GHES instance generate installation tokens via `https://ghes.example.com/api/v3/app/installations/{id}/access_tokens`, not the GitHub.com endpoint.

## Verification

```bash
# Confirm GHES OIDC issuer is reachable from the self-hosted runner
curl https://ghes.example.com/_services/token/.well-known/openid-configuration | jq .issuer

# Confirm GITHUB_API_URL is set correctly in a workflow step
echo "GITHUB_API_URL=$GITHUB_API_URL"   # should be https://ghes.example.com/api/v3

# Test Worker deployment from GHES runner
npx wrangler whoami    # should show account name if CF token is valid
npx wrangler deploy --dry-run --env production
```

## Related

- `github-actions-self-hosted-runners-2026.md`
- `github-actions-oidc-cloudflare-deploy.md`
- `github-app-webhook-workers-handler.md`
- `github-apps-installation-tokens.md`
- `github-actions-egress-firewall.md`

## Sources

- https://docs.github.com/en/enterprise-server@3.12/admin/overview/about-github-enterprise-server
- https://docs.github.com/en/enterprise-server@3.12/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://docs.github.com/en/enterprise-server@3.12/rest/overview/endpoints-available-for-github-apps
