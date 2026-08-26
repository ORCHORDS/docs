# Wrangler Secrets Bulk Migration Between Environments

- **Date:** 2026-08-24
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You have validated a new secrets configuration (updated API keys, rotated database credentials, new third-party tokens) in your `staging` Wrangler environment. You need to promote the same set of secrets to `production` atomically, with a pre-flight diff to confirm which values are changing, without copying plaintext values through shell history, CI logs, or environment variables.

---

## Context

Wrangler environments (`[env.staging]`, `[env.production]` in `wrangler.toml`) maintain isolated secret stores at the Cloudflare API level. There is no built-in `wrangler secret promote` command: secrets set in staging are not automatically propagated to production. A manual process of calling `wrangler secret put` per-secret in production is error-prone and leaves partial state if interrupted.

The correct approach is to read secrets from staging using the Cloudflare REST API (list endpoint returns names only, not values), fetch values from the authoritative vault (Doppler, GitHub Actions secrets, or AWS Secrets Manager), and write them to production using `wrangler secret bulk`. This pipeline keeps plaintext values out of logs, produces an auditable diff of secret names before promotion, and fails atomically if any write errors.

This pattern complements `wrangler-bulk-secrets-deploy-automation.md` (which covers vault→environment import) by addressing the environment→environment promotion flow with a pre-flight diff gate.

---

## 1. List Secrets in Each Environment (Names Only)

```typescript
// scripts/list-env-secrets.ts
// Returns the secret names currently set in a Wrangler environment.
// Secret VALUES are never returned by the Cloudflare API.

export async function listEnvSecrets(
  accountId: string,
  workerName: string,
  apiToken: string
): Promise<string[]> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${workerName}/secrets`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${apiToken}` },
  });

  if (!res.ok) {
    throw new Error(`List secrets failed ${res.status}: ${await res.text()}`);
  }

  const json = (await res.json()) as {
    result: Array<{ name: string; type: string }>;
  };
  return json.result.map((s) => s.name).sort();
}

// Usage:
// const stagingSecrets = await listEnvSecrets(accountId, "my-worker-staging", token);
// const productionSecrets = await listEnvSecrets(accountId, "my-worker", token);
```

Note: Wrangler environments with different `name` overrides in `wrangler.toml` use different script names at the API level:

```toml
# wrangler.toml
name = "my-worker"          # production script name

[env.staging]
name = "my-worker-staging"  # staging script name
```

---

## 2. Pre-Flight Diff: Compare Secret Sets Before Migration

```typescript
// scripts/secret-migration-diff.ts
import { listEnvSecrets } from "./list-env-secrets";

interface SecretDiff {
  onlyInSource: string[];   // present in staging, absent in production
  onlyInTarget: string[];   // present in production, absent in staging (will be orphaned)
  inBoth: string[];         // present in both (values will be overwritten)
}

export async function computeSecretDiff(
  accountId: string,
  sourceWorker: string,   // e.g. "my-worker-staging"
  targetWorker: string,   // e.g. "my-worker"
  apiToken: string
): Promise<SecretDiff> {
  const [sourceNames, targetNames] = await Promise.all([
    listEnvSecrets(accountId, sourceWorker, apiToken),
    listEnvSecrets(accountId, targetWorker, apiToken),
  ]);

  const sourceSet = new Set(sourceNames);
  const targetSet = new Set(targetNames);

  return {
    onlyInSource: sourceNames.filter((n) => !targetSet.has(n)),
    onlyInTarget: targetNames.filter((n) => !sourceSet.has(n)),
    inBoth: sourceNames.filter((n) => targetSet.has(n)),
  };
}

async function main() {
  const accountId = process.env.CF_ACCOUNT_ID!;
  const apiToken = process.env.CF_API_TOKEN!;
  const sourceWorker = process.env.SOURCE_WORKER ?? "my-worker-staging";
  const targetWorker = process.env.TARGET_WORKER ?? "my-worker";

  const diff = await computeSecretDiff(accountId, sourceWorker, targetWorker, apiToken);

  console.log("\n=== Secret Migration Diff ===");
  console.log(`Source: ${sourceWorker}`);
  console.log(`Target: ${targetWorker}\n`);

  if (diff.onlyInSource.length) {
    console.log("NEW secrets to be added to production:");
    diff.onlyInSource.forEach((n) => console.log(`  + ${n}`));
  }

  if (diff.onlyInTarget.length) {
    console.log("\nORPHAN secrets in production not present in staging:");
    diff.onlyInTarget.forEach((n) => console.log(`  ! ${n}  (will NOT be removed)`));
  }

  if (diff.inBoth.length) {
    console.log("\nEXISTING secrets to be overwritten:");
    diff.inBoth.forEach((n) => console.log(`  ~ ${n}`));
  }

  const total = diff.onlyInSource.length + diff.inBoth.length;
  console.log(`\nTotal secrets to write: ${total}`);

  if (diff.onlyInSource.length === 0 && diff.inBoth.length === 0) {
    console.log("No secrets to migrate. Exiting.");
    process.exit(0);
  }
}

main().catch(console.error);
```

---

## 3. Fetch Secret Values from Vault and Build Bulk Payload

```typescript
// scripts/build-secret-bulk-payload.ts
// Reads secret VALUES from Doppler (or any vault) for the staging environment
// and returns a bulk secrets JSON payload scoped to the target environment.

import { execSync } from "child_process";

export interface SecretBulkPayload {

}

export async function buildPayloadFromDoppler(
  dopplerProject: string,
  dopplerConfig: string   // e.g. "staging"
): Promise<SecretBulkPayload> {
  // Doppler CLI: `doppler secrets download --no-file --format json`
  const raw = execSync(
    `doppler secrets download --no-file --format json --project ${dopplerProject} --config ${dopplerConfig}`,
    { encoding: "utf8", env: { ...process.env } }
  );

  const all = JSON.parse(raw) as Record<string, string>;

  // Exclude Doppler meta-keys (DOPPLER_PROJECT, DOPPLER_CONFIG, etc.)
  const secrets: SecretBulkPayload = {};
  for (const [key, value] of Object.entries(all)) {
    if (!key.startsWith("DOPPLER_")) {
      secrets[key] = value;
    }
  }

  return secrets;
}

export async function buildPayloadFromGitHubSecrets(
  secretNames: string[],
  envPrefix: string   // e.g. "STAGING_" — strip this prefix to get canonical name
): Promise<SecretBulkPayload> {
  // GitHub Actions: secrets are injected as env vars with the prefix
  const payload: SecretBulkPayload = {};
  for (const name of secretNames) {
    const envKey = `${envPrefix}${name}`;
    const value = process.env[envKey];
    if (value === undefined) {
      throw new Error(`Missing environment variable: ${envKey}`);
    }
    payload[name] = value;
  }
  return payload;
}
```

---

## 4. Write Bulk Secrets to Production via Wrangler

```typescript
// scripts/migrate-secrets.ts
import { computeSecretDiff } from "./secret-migration-diff";
import { buildPayloadFromDoppler } from "./build-secret-bulk-payload";
import { writeFileSync, unlinkSync } from "fs";
import { execSync } from "child_process";
import { tmpdir } from "os";
import { join } from "path";

async function migrateSecrets() {
  const accountId = process.env.CF_ACCOUNT_ID!;
  const apiToken = process.env.CF_API_TOKEN!;
  const sourceWorker = process.env.SOURCE_WORKER ?? "my-worker-staging";
  const targetWorker = process.env.TARGET_WORKER ?? "my-worker";
  const dopplerProject = process.env.DOPPLER_PROJECT!;
  const dopplerConfig = process.env.DOPPLER_SOURCE_CONFIG ?? "staging";
  const targetEnv = process.env.TARGET_WRANGLER_ENV ?? "production";

  // 1. Compute diff to know which secrets are coming from staging
  const diff = await computeSecretDiff(accountId, sourceWorker, targetWorker, apiToken);
  const secretsToMigrate = [...diff.onlyInSource, ...diff.inBoth];

  if (secretsToMigrate.length === 0) {
    console.log("No secrets to migrate.");
    return;
  }

  console.log(`Migrating ${secretsToMigrate.length} secrets to ${targetWorker}...`);

  // 2. Fetch values from vault for the staging environment
  const allStagingSecrets = await buildPayloadFromDoppler(dopplerProject, dopplerConfig);

  // 3. Build payload containing only secrets present in staging
  const payload: Record<string, string> = {};
  for (const name of secretsToMigrate) {
    if (!(name in allStagingSecrets)) {
      throw new Error(`Secret '${name}' in staging Cloudflare store but missing from Doppler '${dopplerConfig}'`);
    }
    payload[name] = allStagingSecrets[name];
  }

  // 4. Write to temp file and call wrangler secret bulk
  const tmpFile = join(tmpdir(), `secrets-migration-${Date.now()}.json`);
  try {
    writeFileSync(tmpFile, JSON.stringify(payload), { mode: 0o600 });

    execSync(
      `npx wrangler secret bulk "${tmpFile}" --env ${targetEnv}`,
      {
        stdio: "inherit",
        env: {
          ...process.env,
          CLOUDFLARE_API_TOKEN: apiToken,
          CLOUDFLARE_ACCOUNT_ID: accountId,
        },
      }
    );

    console.log(`Successfully migrated ${secretsToMigrate.length} secrets to ${targetEnv}.`);
  } finally {
    // Always delete the plaintext secrets file
    try { unlinkSync(tmpFile); } catch { /* ignore */ }
  }
}

migrateSecrets().catch((err) => {
  console.error("Migration failed:", err.message);
  process.exit(1);
});
```

---

## 5. GitHub Actions Pipeline for Secrets Promotion

```yaml
# .github/workflows/promote-secrets.yml
name: Promote Secrets Staging → Production

on:
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Dry run (diff only, no writes)"
        type: boolean
        default: true

jobs:
  diff:
    name: Pre-flight diff
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"
      - run: npm ci
      - name: Compute and display secret diff
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_READ_ONLY_TOKEN }}
          SOURCE_WORKER: "my-worker-staging"
          TARGET_WORKER: "my-worker"
        run: npx tsx scripts/secret-migration-diff.ts

  promote:
    name: Promote secrets to production
    needs: diff
    if: ${{ github.event.inputs.dry_run == 'false' }}
    runs-on: ubuntu-latest
    environment: production           # requires manual approval
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"
      - run: npm ci
      - name: Install Doppler CLI
        run: |
          curl -Ls https://cli.doppler.com/install.sh | sh
      - name: Migrate secrets
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_DEPLOY_TOKEN }}
          DOPPLER_TOKEN: ${{ secrets.DOPPLER_TOKEN }}
          DOPPLER_PROJECT: "my-platform"
          DOPPLER_SOURCE_CONFIG: "staging"
          SOURCE_WORKER: "my-worker-staging"
          TARGET_WORKER: "my-worker"
          TARGET_WRANGLER_ENV: "production"
        run: npx tsx scripts/migrate-secrets.ts
```

---

## 6. Verify Migration Completeness

```bash
#!/usr/bin/env bash
# scripts/verify-secret-migration.sh
set -euo pipefail

SOURCE_WORKER="${SOURCE_WORKER:-my-worker-staging}"
TARGET_WORKER="${TARGET_WORKER:-my-worker}"

echo "Comparing secret counts..."

SOURCE_COUNT=$(
  curl -s \
    "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${SOURCE_WORKER}/secrets" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result | length'
)

TARGET_COUNT=$(
  curl -s \
    "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${TARGET_WORKER}/secrets" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result | length'
)

echo "Staging secrets: ${SOURCE_COUNT}"
echo "Production secrets: ${TARGET_COUNT}"

if [ "$TARGET_COUNT" -lt "$SOURCE_COUNT" ]; then
  echo "WARNING: Production has fewer secrets than staging (${TARGET_COUNT} < ${SOURCE_COUNT})"
  exit 1
fi

echo "OK: Production has at least as many secrets as staging."
```

---

## Anti-patterns

- **Listing production secrets, then deleting secrets missing from staging** — `wrangler secret bulk` does not delete; any delete step risks removing secrets production depends on that were intentionally not in staging.
- **Echoing secret values in CI logs** — the bulk payload file contains plaintext. Always write to `tmpdir()` with mode `0o600` and delete it in a `finally` block.
- **Running migration without a pre-flight diff** — without a diff, you cannot distinguish a successful promotion from a partial write if CI is interrupted mid-run.
- **Using `wrangler secret list` output to determine what to migrate** — `secret list` returns names without values. Always fetch values from the authoritative vault (Doppler/Vault), not from another Cloudflare environment.

---

## Gotchas

- `wrangler secret bulk` is available from **Wrangler v3.5+**. Earlier versions require individual `wrangler secret put` calls.
- Secret names are case-sensitive and cannot contain spaces. Validate names with `/^[A-Z_][A-Z0-9_]*$/` before bulk write.
- The Cloudflare API `/secrets` endpoint returns a `result` array of `{ name, type }` — the `type` field is always `"secret_text"` for secrets created via wrangler. Bindings (`kv_namespaces`, `d1_databases`) also appear in the `/bindings` endpoint but are distinct from secrets.
- `wrangler secret bulk` does not return a per-secret success/failure breakdown. If any secret fails validation (e.g., value too large), the entire bulk call may fail without clear error messaging. Test with a small subset first.

---

## Verification

```bash
# 1. Confirm production secret count after migration
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/my-worker/secrets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '[.result[].name] | sort'

# 2. Smoke-test an endpoint that requires a migrated secret
curl -s -o /dev/null -w "%{http_code}" \
  https://api.example.com/health/secrets

# 3. Check Worker deployment logs for secret-binding errors
wrangler tail my-worker --format=json \
  | jq 'select(.exceptions[].message | test("secret|binding"; "i"))'
```

---

## Related

- `wrangler-bulk-secrets-deploy-automation.md` — bulk secrets import from vault into a single environment
- `workers-secrets-bulk-rotation-automation-ci.md` — bulk secret rotation without environment promotion
- `secrets-management-wrangler-vault.md` — vault integration strategy for Wrangler secrets
- `wrangler-environments-promotion-pipeline.md` — full environment promotion pipeline including bindings and config

---

## Sources

- Cloudflare Docs — wrangler secret bulk: https://developers.cloudflare.com/workers/wrangler/commands/#secret-bulk
- Cloudflare API — Workers Secrets: https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/secrets/
- Doppler CLI Docs — secrets download: https://docs.doppler.com/docs/cli
