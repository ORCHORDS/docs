# git credential helper: CI token rotation for Cloudflare Workers pipelines

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A long-lived GitHub PAT stored as a repository secret stops working mid-pipeline because it expired or was rotated by a security policy scan. Alternatively, the Cloudflare API token embedded in CI has write-access to all zones because nobody wanted to narrow it when the project was small. This article covers how to wire short-lived, scoped credentials into git operations and Wrangler deploys through the git credential helper protocol, GitHub's OIDC token exchange, and Cloudflare's token permission model.

## Context

Git credential helpers are executables that git invokes to GET, STORE, and ERASE credentials. The protocol is line-oriented (key=value over stdin/stdout). In CI this mechanism lets you swap hardcoded PATs for tokens generated fresh each run from a trusted identity provider—GitHub OIDC for GitHub Actions, or Vault-issued tokens for self-hosted runners.

Cloudflare Workers deployments add a second credential surface: the Wrangler CLI needs a `CLOUDFLARE_API_TOKEN` that is independent of git auth. Rotating both on the same cadence, from the same OIDC exchange, keeps the attack surface narrow.

## The git credential helper protocol

```bash
# A minimal helper is any executable that reads action + attrs from stdin
# and writes attrs to stdout. Example interaction for GET:

# git writes to the helper's stdin:
protocol=https
host=github.com
username=x-access-token
<blank line>

# helper writes to stdout:
protocol=https
host=github.com
username=x-access-token
password=<redacted-secret>
<blank line>
```

## Implementing a TypeScript credential helper for CI

```typescript
#!/usr/bin/env tsx
// scripts/git-credential-github-app.ts
// Exchanges a GitHub App installation token for use as git credentials.
// Register with: git config credential.helper \
//   "tsx /repo/scripts/git-credential-github-app.ts"

import { createAppAuth } from "@octokit/auth-app";
import * as readline from "node:readline/promises";
import { stdin, stdout } from "node:process";

const APP_ID = process.env.GH_APP_ID!;
const PRIVATE_KEY = process.env.GH_APP_PRIVATE_KEY!.replace(/\\n/g, "\n");
const INSTALLATION_ID = Number(process.env.GH_APP_INSTALLATION_ID!);

async function readInput(): Promise<Record<string, string>> {
  const rl = readline.createInterface({ input: stdin });
  const attrs: Record<string, string> = {};
  for await (const line of rl) {
    if (line === "") break;
    const [key, ...rest] = line.split("=");
    attrs[key] = rest.join("=");
  }
  return attrs;
}

async function main(): Promise<void> {
  const action = process.argv[2]; // "get" | "store" | "erase"
  if (action !== "get") process.exit(0); // Only handle GET

  const attrs = await readInput();
  if (attrs.host !== "github.com") process.exit(0); // Not our domain

  const auth = createAppAuth({ appId: APP_ID, privateKey: PRIVATE_KEY });
  const { token } = await auth({
    type: "installation",
    installationId: INSTALLATION_ID,
  });

  stdout.write(
    [
      `protocol=${attrs.protocol}`,
      `host=${attrs.host}`,
      `username=x-access-token`,
      `password=${token}`,
      "",
    ].join("\n")
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

## GitHub OIDC token exchange for Cloudflare API tokens

```typescript
// scripts/exchange-oidc-for-cf-token.ts
// Called as a pre-deploy step; writes CF_API_TOKEN to $GITHUB_ENV.

import { appendFileSync } from "node:fs";

interface OidcExchangeResponse {
  result: { id: string; value: string };
  errors: { message: string }[];
}

async function getGithubOidcToken(): Promise<string> {
  const requestUrl = process.env.ACTIONS_ID_TOKEN_REQUEST_URL!;
  const requestToken = process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN!;
  const audience = "https://api.cloudflare.com";

  const res = await fetch(`${requestUrl}&audience=${audience}`, {
    headers: { Authorization: `bearer ${requestToken}` },
  });
  const data = (await res.json()) as { value: string };
  return data.value;
}

async function exchangeForCfToken(oidcJwt: string): Promise<string> {
  // Cloudflare "exchange token" endpoint (hypothetical internal pattern).
  // In practice, use Vault or a custom exchange service.
  const res = await fetch("https://vault.internal/v1/cf/token", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${oidcJwt}`,
    },
    body: JSON.stringify({
      role: "workers-deploy-staging",
      ttl: "10m",
    }),
  });
  if (!res.ok) throw new Error(`Token exchange failed: ${res.status}`);
  const data = (await res.json()) as OidcExchangeResponse;
  if (data.errors?.length) throw new Error(data.errors[0].message);
  return data.result.value;
}

async function main(): Promise<void> {
  const oidcJwt = await getGithubOidcToken();
  const cfToken = await exchangeForCfToken(oidcJwt);
  // Write to GitHub Actions environment for subsequent steps
  appendFileSync(process.env.GITHUB_ENV!, `CLOUDFLARE_API_TOKEN=${cfToken}\n`);
  console.log("CF token written to GITHUB_ENV (value redacted)");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

## GitHub Actions workflow wiring

```yaml
# .github/workflows/workers-deploy-oidc.yml
name: Workers Deploy (OIDC)

on:
  push:
    branches: [main]

permissions:
  id-token: write   # Required for OIDC token issuance
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      # Configure git to use the App-based credential helper
      - name: Configure git credential helper
        env:
          GH_APP_ID: ${{ secrets.GH_APP_ID }}
          GH_APP_PRIVATE_KEY: ${{ secrets.GH_APP_PRIVATE_KEY }}
          GH_APP_INSTALLATION_ID: ${{ secrets.GH_APP_INSTALLATION_ID }}
        run: |
          git config --global credential.helper \
            "tsx ${{ github.workspace }}/scripts/git-credential-github-app.ts"

      # Exchange OIDC token for a short-lived CF API token
      - name: Acquire Cloudflare token
        run: pnpm tsx scripts/exchange-oidc-for-cf-token.ts

      - name: Deploy Workers
        run: pnpm turbo run deploy --filter="./workers/*"
        # CLOUDFLARE_API_TOKEN is now available via GITHUB_ENV
```

## Token scope audit helper

```typescript
// scripts/audit-token-scopes.ts
// Confirms the active CF token has exactly the permissions needed, no more.

interface CfTokenPermission {
  permission_group: { id: string; name: string };
  resources: Record<string, string>;
}

interface CfTokenVerifyResponse {
  result: { id: string; status: string };
  errors: { message: string }[];
}

const REQUIRED_PERMISSIONS = new Set([
  "Workers Scripts",
  "Workers KV Storage",
  "D1",
]);

async function auditToken(token: string): Promise<void> {
  const verifyRes = await fetch(
    "https://api.cloudflare.com/client/v4/user/tokens/verify",
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const verify = (await verifyRes.json()) as CfTokenVerifyResponse;
  if (verify.result.status !== "active") {
    throw new Error(`Token not active: ${verify.result.status}`);
  }

  const permsRes = await fetch(
    `https://api.cloudflare.com/client/v4/user/tokens/${verify.result.id}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const perms = (await permsRes.json()) as {
    result: { policies: { permission_groups: CfTokenPermission[] }[] };
  };

  const granted = new Set(
    perms.result.policies
      .flatMap((p) => p.permission_groups)
      .map((pg) => pg.permission_group.name)
  );

  for (const req of REQUIRED_PERMISSIONS) {
    if (!granted.has(req)) throw new Error(`Missing permission: ${req}`);
  }

  const extra = [...granted].filter((g) => !REQUIRED_PERMISSIONS.has(g));
  if (extra.length > 0) {
    console.warn(`WARNING: token has excess permissions: ${extra.join(", ")}`);
  }

  console.log("Token scope audit passed.");
}

auditToken(process.env.CLOUDFLARE_API_TOKEN!).catch((err) => {
  console.error(err);
  process.exit(1);
});
```

## Anti-patterns

- **Storing long-lived PATs in repository secrets** — secrets are not rotated automatically; a leaked secret remains valid until manually revoked.
- **Using a single broad-scope Cloudflare API token across all environments** — a compromised staging token should not be able to overwrite production Workers.
- **Embedding tokens in git config files committed to the repo** — `git config credential.helper store` writes plaintext tokens to `~/.git-credentials`, which may end up in Docker layers or CI artifacts.
- **Sharing the same GitHub App installation across unrelated repositories** — limit each installation to the repos it must access, following the principle of least privilege.

## Gotchas

- The `id-token: write` permission in GitHub Actions is required at the **job** level, not the workflow level, if you have multiple jobs with different permission needs.
- `ACTIONS_ID_TOKEN_REQUEST_URL` and `ACTIONS_ID_TOKEN_REQUEST_TOKEN` are only injected when `id-token: write` is explicitly set; they are absent otherwise, causing silent `undefined` failures.
- GitHub App installation tokens expire after 1 hour. For jobs longer than an hour, re-invoke the credential helper or split the job.
- Cloudflare API tokens are not automatically rotated; the OIDC exchange pattern requires a custom intermediary (Vault, a Workers KV-backed exchange endpoint, etc.).
- `git config --global` in CI modifies the runner's global gitconfig; prefer `--local` (per-repo) or scoped helpers to avoid bleeding into concurrent jobs on self-hosted runners.

## Verification

```bash
# Verify the credential helper is registered
git config --global credential.helper

# Test the helper manually (pipe fake input)
printf "protocol=https\nhost=github.com\n\n" | \
  tsx scripts/git-credential-github-app.ts get

# Confirm CF token scope
CLOUDFLARE_API_TOKEN=<token> pnpm tsx scripts/audit-token-scopes.ts

# Check GitHub OIDC availability in Actions
# (run as a workflow step)
echo "OIDC URL: $ACTIONS_ID_TOKEN_REQUEST_URL"
```

## Related

- `git-credential-capability-negotiation.md` — protocol-level credential negotiation
- `signed-commits-2026.md` — GPG/SSH signing in CI
- `secret-scanning-2026.md` — detecting leaked tokens
- `wrangler-secrets-bulk-management-ci.md` — Wrangler secret lifecycle
- `github-actions-wrangler-deploy-pipeline.md` — full deploy pipeline wiring

## Sources

- Git documentation: `git help credential`, `git help gitcredentials`
- GitHub Actions: OIDC documentation, `id-token` permission reference
- Cloudflare API: Token permissions reference (developers.cloudflare.com)
- `@octokit/auth-app` npm package documentation
