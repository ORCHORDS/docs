# Wrangler Bulk Secrets Deploy Automation

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You maintain dozens of Workers across multiple environments (staging, production) and need to seed or rotate a large set of secrets atomically in CI. Calling `wrangler secret put` interactively one-by-one is error-prone, blocks pipelines, and leaves partial state when interrupted mid-run.

---

## Context

Wrangler exposes `wrangler secret put` for individual secrets and `wrangler secret bulk` (since Wrangler v3.5) for batch import from a JSON file. Combining this with GitHub Actions OIDC and environment-scoped secret stores gives a fully automated, auditable secrets-promotion pipeline with no plaintext values in logs or CI config.

Secrets live at the Worker level, scoped per Wrangler environment. They are distinct from `vars` (which appear in `wrangler.toml` and are non-sensitive) and from KV/D1/R2 bindings.

---

## Staging Secrets File Generation

Never commit secret values to source control. Instead, generate a transient secrets JSON at deploy time from a vault (GitHub Actions encrypted secrets, Doppler, HashiCorp Vault):

```typescript
// scripts/gen-secrets-bulk.ts
import { writeFileSync } from "fs";

interface SecretMap {

}

function collectFromEnv(keys: string[]): SecretMap {
  const missing: string[] = [];
  const result: SecretMap = {};

  for (const key of keys) {
    const value = process.env[key];
    if (!value) {
      missing.push(key);
    } else {
      result[key] = value;
    }
  }

  if (missing.length > 0) {
    console.error(`Missing env vars: ${missing.join(", ")}`);
    process.exit(1);
  }

  return result;
}

const REQUIRED_SECRETS = [
  "DATABASE_URL",
  "API_KEY_STRIPE",
  "API_KEY_SENDGRID",
  "JWT_SECRET",
  "WEBHOOK_SIGNING_SECRET",
];

const secrets = collectFromEnv(REQUIRED_SECRETS);
writeFileSync("secrets.bulk.json", JSON.stringify(secrets, null, 2));
console.log(`Generated secrets bulk file with ${Object.keys(secrets).length} keys`);
```

---

## Bulk Push via Wrangler

```bash
# Push all secrets to staging environment
wrangler secret bulk secrets.bulk.json --env staging --name my-worker

# Push all secrets to production environment
wrangler secret bulk secrets.bulk.json --env production --name my-worker
```

The bulk command reads a flat JSON object `{ "KEY": "value" }` and upserts each key. Existing secrets not in the file are left unchanged (no implicit deletion).

---

## GitHub Actions Workflow

```yaml
# .github/workflows/deploy-secrets.yml
name: Deploy Worker Secrets

on:
  push:
    branches: [main]
    paths:
      - "scripts/gen-secrets-bulk.ts"
      - ".github/workflows/deploy-secrets.yml"
  workflow_dispatch:
    inputs:
      environment:
        description: "Target environment"
        required: true
        type: choice
        options: [staging, production]

permissions:
  id-token: write   # OIDC for Cloudflare
  contents: read

jobs:
  push-secrets:
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment || 'staging' }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install Wrangler
        run: npm install -g wrangler@latest

      - name: Generate secrets bulk file
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          API_KEY_STRIPE: ${{ secrets.API_KEY_STRIPE }}
          API_KEY_SENDGRID: ${{ secrets.API_KEY_SENDGRID }}
          JWT_SECRET: ${{ secrets.JWT_SECRET }}
          WEBHOOK_SIGNING_SECRET: ${{ secrets.WEBHOOK_SIGNING_SECRET }}
        run: npx ts-node scripts/gen-secrets-bulk.ts

      - name: Push secrets to Cloudflare
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          wrangler secret bulk secrets.bulk.json \
            --env ${{ github.event.inputs.environment || 'staging' }} \
            --name my-worker

      - name: Clean up secrets file
        if: always()
        run: rm -f secrets.bulk.json
```

---

## Verifying Secrets After Push

```typescript
// scripts/verify-secrets.ts
import { execSync } from "child_process";

const EXPECTED_SECRETS = [
  "DATABASE_URL",
  "API_KEY_STRIPE",
  "API_KEY_SENDGRID",
  "JWT_SECRET",
  "WEBHOOK_SIGNING_SECRET",
];

function listWorkerSecrets(workerName: string, env: string): string[] {
  const output = execSync(
    `wrangler secret list --name ${workerName} --env ${env} --json`,
    { encoding: "utf-8" }
  );
  const secrets: Array<{ name: string }> = JSON.parse(output);
  return secrets.map((s) => s.name);
}

const env = process.argv[2] || "staging";
const worker = process.argv[3] || "my-worker";
const actual = listWorkerSecrets(worker, env);
const missing = EXPECTED_SECRETS.filter((k) => !actual.includes(k));

if (missing.length > 0) {
  console.error(`Secrets missing on ${worker}/${env}: ${missing.join(", ")}`);
  process.exit(1);
}

console.log(`All ${EXPECTED_SECRETS.length} secrets verified on ${worker}/${env}`);
```

---

## Multi-Worker Bulk Push

```typescript
// scripts/push-all-workers.ts
import { execSync } from "child_process";
import { writeFileSync, unlinkSync } from "fs";

interface WorkerSecretSpec {
  workerName: string;
  environment: string;
  secretKeys: string[];
}

const WORKERS: WorkerSecretSpec[] = [
  { workerName: "api-worker", environment: "production", secretKeys: ["DATABASE_URL", "JWT_SECRET"] },
  { workerName: "webhook-worker", environment: "production", secretKeys: ["WEBHOOK_SIGNING_SECRET", "API_KEY_STRIPE"] },
  { workerName: "email-worker", environment: "production", secretKeys: ["API_KEY_SENDGRID"] },
];

for (const spec of WORKERS) {
  const secretMap: Record<string, string> = {};
  for (const key of spec.secretKeys) {
    const value = process.env[key];
    if (!value) throw new Error(`Missing env var: ${key}`);
    secretMap[key] = value;
  }

  const tmpFile = `secrets-${spec.workerName}.json`;
  writeFileSync(tmpFile, JSON.stringify(secretMap));

  try {
    execSync(
      `wrangler secret bulk ${tmpFile} --name ${spec.workerName} --env ${spec.environment}`,
      { stdio: "inherit" }
    );
    console.log(`Pushed ${spec.secretKeys.length} secrets to ${spec.workerName}/${spec.environment}`);
  } finally {
    unlinkSync(tmpFile);
  }
}
```

---

## Anti-patterns

- **Committing secrets.json to git** — even temporarily. Use `secrets.bulk.json` in `.gitignore` and generate it at CI runtime only.
- **Using `wrangler secret put` in a loop** — each call makes a separate API request; `bulk` is atomic and faster.
- **Storing secrets in `wrangler.toml` under `[vars]`** — `vars` are plaintext in the config file and visible in `wrangler deploy` output.
- **Not cleaning up the bulk file after use** — add `if: always()` cleanup step so the file is removed even on failure.
- **Pushing all secrets to all workers** — scope secret keys per worker to follow least-privilege.

---

## Gotchas

- `wrangler secret bulk` does NOT delete secrets absent from the JSON file; deletions require explicit `wrangler secret delete`.
- The `--json` flag on `wrangler secret list` requires Wrangler v3.9+.
- Secrets pushed via bulk are immediately active on the next request; there is no deployment event — the worker binary does not redeploy.
- GitHub Actions environment protection rules (required reviewers) apply to `environment:` blocks, gating the production secrets push.
- Wrangler bulk accepts only a flat JSON object; nested structures are not supported.

---

## Verification

```bash
# List all secrets currently set on the worker
wrangler secret list --name my-worker --env production --json | jq '.[].name'

# Confirm expected count matches
EXPECTED=5
ACTUAL=$(wrangler secret list --name my-worker --env production --json | jq 'length')
[ "$ACTUAL" -eq "$EXPECTED" ] && echo "OK" || echo "MISMATCH: expected $EXPECTED, got $ACTUAL"
```

---

## Related

- `secrets-management-wrangler-vault.md`
- `workers-secrets-rotation-zero-downtime.md`
- `wrangler-environments-promotion-pipeline.md`
- `oidc-federated-deploy-credentials.md`
- `env-binding-precedence.md`

---

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#secret-bulk
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/workers/wrangler/configuration/#secrets
