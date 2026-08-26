# Workers Secrets Sync in Deploy Pipeline from Vault

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Secrets for a Cloudflare Worker (API keys, database credentials, signing keys) are managed in
an external secret manager — HashiCorp Vault, AWS Secrets Manager, or GitHub Actions Secrets —
but the `wrangler secret put` workflow requires manual copy-paste or a human in the loop.
After a secrets rotation the Worker is redeployed but the new secret value is not automatically
picked up, causing auth failures until someone manually re-runs `wrangler secret put`. You need
a CI/CD pipeline step that reads from the source-of-truth vault, syncs secrets to Workers, and
fails the deploy if any secret is missing or stale.

---

## Context

`wrangler secret put` is idempotent but takes a single secret at a time and reads the value
from stdin, making it awkward to drive from a script. The Cloudflare REST API provides a bulk
secrets endpoint (`PUT /accounts/:id/workers/scripts/:name/secrets`) that accepts a JSON array
of `{ name, text, type }` objects in a single request — far more pipeline-friendly.

The pattern is:
1. Authenticate to the external vault with OIDC or a machine credential.
2. Read the required secrets (by name) into memory — never write to disk.
3. Call the Cloudflare bulk secrets API.
4. Verify that each secret name exists on the deployed Worker before proceeding.
5. Deploy the Worker code only after secrets are confirmed in place.

---

## 1. Vault client abstraction

```typescript
// src/vault/types.ts
export interface VaultClient {
  getSecret(key: string): Promise<string>;
  getSecretMap(keys: string[]): Promise<Record<string, string>>;
}
```

```typescript
// src/vault/github-actions.ts  — reads from GitHub Actions secrets via env
import type { VaultClient } from "./types.js";

export class GitHubActionsVault implements VaultClient {
  async getSecret(key: string): Promise<string> {
    const val = process.env[key];
    if (!val) throw new Error(`Secret "${key}" not found in environment.`);
    return val;
  }

  async getSecretMap(keys: string[]): Promise<Record<string, string>> {
    const result: Record<string, string> = {};
    for (const key of keys) {
      result[key] = await this.getSecret(key);
    }
    return result;
  }
}
```

```typescript
// src/vault/hashicorp.ts  — reads from HashiCorp Vault via HTTP API
import type { VaultClient } from "./types.js";

interface VaultReadResponse {
  data: { data: Record<string, string> };
}

export class HashiCorpVault implements VaultClient {
  constructor(
    private readonly vaultAddr: string,
    private readonly vaultToken: string,
    private readonly mountPath: string
  ) {}

  async getSecret(key: string): Promise<string> {
    const map = await this.getSecretMap([key]);
    return map[key];
  }

  async getSecretMap(keys: string[]): Promise<Record<string, string>> {
    const url = `${this.vaultAddr}/v1/${this.mountPath}/data/workers`;
    const res = await fetch(url, {
      headers: { "X-Vault-Token": this.vaultToken },
    });

    if (!res.ok) {
      throw new Error(`Vault fetch failed: HTTP ${res.status}`);
    }

    const body: VaultReadResponse = await res.json() as VaultReadResponse;
    const data = body.data.data;

    const result: Record<string, string> = {};
    for (const key of keys) {
      if (!(key in data)) throw new Error(`Key "${key}" not found in Vault path.`);
      result[key] = data[key];
    }
    return result;
  }
}
```

---

## 2. Bulk-push secrets to Workers

```typescript
// scripts/sync-secrets.ts
import type { VaultClient } from "../src/vault/types.js";

interface CloudflareSecret {
  name: string;
  text: string;
  type: "secret_text";
}

/** Secret names in Workers that map to vault keys. */
const SECRET_MAP: Record<string, string> = {
  // workers_secret_name: vault_key
  DATABASE_URL:       "DATABASE_URL",
  JWT_SIGNING_KEY:    "JWT_SIGNING_KEY",
  STRIPE_SECRET_KEY:  "STRIPE_SECRET_KEY",
  SENDGRID_API_KEY:   "SENDGRID_API_KEY",
};

async function syncSecretsToWorker(
  vault: VaultClient,
  accountId: string,
  workerName: string,
  apiToken: string
): Promise<void> {
  const vaultKeys = Object.values(SECRET_MAP);
  const values = await vault.getSecretMap(vaultKeys);

  const secrets: CloudflareSecret[] = Object.entries(SECRET_MAP).map(
    ([workerKey, vaultKey]) => ({
      name: workerKey,
      text: values[vaultKey],
      type: "secret_text" as const,
    })
  );

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${workerName}/secrets`,
    {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(secrets),
    }
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to sync secrets: HTTP ${res.status} — ${body}`);
  }

  console.log(`Synced ${secrets.length} secret(s) to ${workerName}.`);

  // Do NOT log secret values — log only names.
  secrets.forEach((s) => console.log(`  • ${s.name}`));
}

export { syncSecretsToWorker };
```

---

## 3. Verify secrets are registered before deploying

```typescript
// scripts/verify-secrets.ts
interface SecretListResponse {
  result: Array<{ name: string; type: string }>;
  success: boolean;
}

async function verifySecretsExist(
  accountId: string,
  workerName: string,
  apiToken: string,
  expectedNames: string[]
): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${workerName}/secrets`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );

  const body: SecretListResponse = await res.json() as SecretListResponse;
  const existing = new Set(body.result.map((s) => s.name));

  const missing = expectedNames.filter((n) => !existing.has(n));
  if (missing.length > 0) {
    throw new Error(
      `Deploy blocked — missing secrets on Worker "${workerName}": ${missing.join(", ")}`
    );
  }

  console.log(`All ${expectedNames.length} required secret(s) verified ✓`);
}

export { verifySecretsExist };
```

---

## 4. Full pipeline orchestration

```typescript
// scripts/deploy-pipeline.ts
import { GitHubActionsVault } from "../src/vault/github-actions.js";
import { syncSecretsToWorker } from "./sync-secrets.js";
import { verifySecretsExist } from "./verify-secrets.js";
import { execSync } from "node:child_process";

const ACCOUNT_ID  = process.env.CF_ACCOUNT_ID!;
const API_TOKEN   = process.env.CF_API_TOKEN!;
const WORKER_NAME = process.env.WORKER_NAME ?? "my-worker";

const vault = new GitHubActionsVault();

// 1. Sync secrets from vault → Workers (before the bundle deploy).
await syncSecretsToWorker(vault, ACCOUNT_ID, WORKER_NAME, API_TOKEN);

// 2. Confirm all secrets are in place.
await verifySecretsExist(ACCOUNT_ID, WORKER_NAME, API_TOKEN, [
  "DATABASE_URL",
  "JWT_SIGNING_KEY",
  "STRIPE_SECRET_KEY",
  "SENDGRID_API_KEY",
]);

// 3. Deploy the Worker bundle only after secrets gate passes.
execSync("pnpm wrangler deploy", {
  env: { ...process.env, CLOUDFLARE_API_TOKEN: API_TOKEN },
  stdio: "inherit",
});

console.log("Deploy complete with all secrets in sync.");
```

---

## 5. OIDC-based Vault auth in GitHub Actions (no long-lived tokens)

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Authenticate to HashiCorp Vault
        uses: hashicorp/vault-action@v3
        id: vault
        with:
          url: ${{ secrets.VAULT_ADDR }}
          method: jwt
          role: workers-deploy
          secrets: |
            secret/data/workers DATABASE_URL | DATABASE_URL ;
            secret/data/workers JWT_SIGNING_KEY | JWT_SIGNING_KEY ;
            secret/data/workers STRIPE_SECRET_KEY | STRIPE_SECRET_KEY ;
            secret/data/workers SENDGRID_API_KEY | SENDGRID_API_KEY

      - name: Sync secrets & deploy
        run: pnpm tsx scripts/deploy-pipeline.ts
        env:
          CF_API_TOKEN:   ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID:  ${{ secrets.CF_ACCOUNT_ID }}
          DATABASE_URL:   ${{ steps.vault.outputs.DATABASE_URL }}
          JWT_SIGNING_KEY: ${{ steps.vault.outputs.JWT_SIGNING_KEY }}
          STRIPE_SECRET_KEY: ${{ steps.vault.outputs.STRIPE_SECRET_KEY }}
          SENDGRID_API_KEY: ${{ steps.vault.outputs.SENDGRID_API_KEY }}
```

---

## Anti-patterns

- **Writing secrets to disk** (`fs.writeFileSync`, temp files): even with `chmod 600`, secrets
  persist in the runner's filesystem. Keep all secret values in memory only.
- **Logging secret values**: `console.log(secrets)` in a failed deploy exposes values in CI
  logs. Log only the names, never the values.
- **Deploying before syncing secrets**: if the Worker bundle is deployed first and starts
  receiving traffic before secrets arrive, requests may fail with missing-env errors.
  Always sync and verify before the `wrangler deploy` call.
- **Using `wrangler secret put` in a loop**: the single-secret endpoint serializes network
  round-trips. The bulk PUT endpoint uploads all secrets atomically in one request.

---

## Gotchas

- The Cloudflare bulk secrets PUT endpoint **replaces** the entire secret set for the Worker.
  Omitting a secret name that currently exists will delete it. Always enumerate all required
  secrets, not just the ones that changed.
- Secret values are write-only in the Cloudflare API: the list endpoint returns names but not
  values. Verification can only confirm presence, not content. Confirm content by running an
  authenticated smoke-test against the Worker itself.
- GitHub Actions masks secret values in logs automatically. When using `vault-action`, outputs
  are also masked. For other vault integrations, call `core.setSecret(value)` from
  `@actions/core` to register the masking pattern manually.

---

## Verification

```bash
# List secrets currently set on the Worker
curl -s -X GET \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/secrets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[].name'

# Confirm Worker is using the updated secret (smoke test)
curl -s -H "Authorization: Bearer test-jwt" https://api.example.com/me | jq .
```

---

## Related

- `secrets-management-wrangler-vault.md`
- `workers-secrets-bulk-rotation-automation-ci.md`
- `wrangler-bulk-secrets-deploy-automation.md`
- `wrangler-ci-secrets-audit-pre-deploy-scan.md`
- `secrets-rotation-deploy-coordination.md`

---

## Sources

- Cloudflare Workers Secrets API (bulk PUT): https://developers.cloudflare.com/api/operations/worker-secrets-put-secrets
- HashiCorp Vault Action for GitHub Actions: https://github.com/hashicorp/vault-action
- Cloudflare Workers Secrets docs: https://developers.cloudflare.com/workers/configuration/secrets/
- GitHub OIDC token for Vault authentication: https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect
