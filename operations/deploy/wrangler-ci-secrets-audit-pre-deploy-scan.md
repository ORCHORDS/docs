# Wrangler CI Secrets Audit Pre-Deploy Scan

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Before deploying a Cloudflare Worker to production, CI must verify that every secret declared in `wrangler.toml` actually exists in the target environment, that no secret keys have been accidentally hard-coded into source files, and that no stale secrets remain bound to the Worker after a rename or removal. Without this scan, deploys silently ship Workers with missing secrets that fail at runtime or with credentials committed to source.

## Context
Cloudflare Workers secrets are stored server-side per-environment via `wrangler secret put`. They are deliberately excluded from `wrangler.toml` values. This creates a drift risk: a developer renames a secret in `wrangler.toml` but forgets to create the renamed secret in the Cloudflare dashboard, and the deploy succeeds while the Worker breaks at runtime. A pre-deploy CI job that audits secrets before `wrangler deploy` catches this class of error early.

## Step 1 — Parse Required Secrets from wrangler.toml

```typescript
// scripts/parse-required-secrets.ts
// Extracts all secret names declared in wrangler.toml across all environments.
import fs from "node:fs";
import { parse as parseToml } from "smol-toml"; // npm i smol-toml

interface WranglerEnv {
  vars?: Record<string, string>;
  // wrangler.toml doesn't store secret values, but [secrets] key lists names
  secrets?: string[];
}

interface WranglerConfig extends WranglerEnv {
  env?: Record<string, WranglerEnv>;
}

function extractSecretNames(config: WranglerConfig, targetEnv?: string): string[] {
  const names = new Set<string>(config.secrets ?? []);

  if (targetEnv && config.env?.[targetEnv]?.secrets) {
    for (const s of config.env[targetEnv].secrets!) {
      names.add(s);
    }
  } else if (config.env) {
    for (const envConfig of Object.values(config.env)) {
      for (const s of envConfig.secrets ?? []) {
        names.add(s);
      }
    }
  }

  return [...names].sort();
}

const raw = fs.readFileSync("wrangler.toml", "utf8");
const config = parseToml(raw) as WranglerConfig;
const targetEnv = process.argv[2]; // e.g. "production"
const required = extractSecretNames(config, targetEnv);

fs.writeFileSync(
  "dist/required-secrets.json",
  JSON.stringify({ required, target_env: targetEnv ?? "default" }, null, 2)
);

console.log("Required secrets:", required);
```

## Step 2 — Fetch Existing Secrets from Cloudflare API

```typescript
// scripts/fetch-remote-secrets.ts
// Lists secret names currently bound to the target Worker (values are never returned).
import fs from "node:fs";

async function fetchRemoteSecrets(
  accountId: string,
  workerName: string,
  apiToken: string,
  envName?: string
): Promise<string[]> {
  // For named environments the URL uses the env suffix pattern
  const scriptName = envName ? `${workerName}-${envName}` : workerName;

  const url =
    `https://api.cloudflare.com/client/v4/accounts/${accountId}` +
    `/workers/scripts/${scriptName}/secrets`;

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${apiToken}` },
  });

  if (!res.ok) {
    if (res.status === 404) {
      console.warn(`Worker ${scriptName} not found — first deploy, no existing secrets.`);
      return [];
    }
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }

  const json = (await res.json()) as {
    result: Array<{ name: string; type: string }>;
  };

  return json.result.map((s) => s.name).sort();
}

const remote = await fetchRemoteSecrets(
  process.env.CF_ACCOUNT_ID!,
  process.env.WORKER_NAME!,
  process.env.CF_API_TOKEN!,
  process.argv[2]
);

fs.writeFileSync("dist/remote-secrets.json", JSON.stringify({ remote }, null, 2));
console.log("Remote secrets:", remote);
```

## Step 3 — Diff and Report

```typescript
// scripts/audit-secrets.ts
import fs from "node:fs";

const { required } = JSON.parse(
  fs.readFileSync("dist/required-secrets.json", "utf8")
) as { required: string[]; target_env: string };

const { remote } = JSON.parse(
  fs.readFileSync("dist/remote-secrets.json", "utf8")
) as { remote: string[] };

const requiredSet = new Set(required);
const remoteSet = new Set(remote);

const missing = required.filter((s) => !remoteSet.has(s));
const stale = remote.filter((s) => !requiredSet.has(s));
const present = required.filter((s) => remoteSet.has(s));

let exitCode = 0;
const lines: string[] = ["## Secrets Audit Report\n"];

if (present.length > 0) {
  lines.push(`### ✓ Present (${present.length})`);
  lines.push(...present.map((s) => `- ${s}`));
  lines.push("");
}

if (missing.length > 0) {
  exitCode = 1;
  lines.push(`### ✗ Missing — will cause runtime failure (${missing.length})`);
  lines.push(...missing.map((s) => `- **${s}**`));
  lines.push("\nRun: `wrangler secret put <NAME>` for each missing secret.");
  lines.push("");
}

if (stale.length > 0) {
  lines.push(`### ⚠ Stale — bound but not declared in wrangler.toml (${stale.length})`);
  lines.push(...stale.map((s) => `- ${s}`));
  lines.push(
    "\nConsider: `wrangler secret delete <NAME>` to remove stale secrets after verifying."
  );
}

const report = lines.join("\n");
fs.writeFileSync("dist/secrets-audit-report.md", report);
console.log(report);

if (exitCode !== 0) {
  console.error(`\nAudit FAILED: ${missing.length} missing secret(s). Deploy blocked.`);
  process.exit(exitCode);
}

console.log("\nAudit PASSED.");
```

## Step 4 — Hardcoded Secret Scan (Regex-based)

```bash
#!/usr/bin/env bash
# scripts/scan-hardcoded-secrets.sh
# Fails CI if common secret patterns are found in source files.
set -euo pipefail

SCAN_PATHS=${SCAN_PATHS:-"src/"}
EXCLUDE_PATTERNS="*.test.ts|*.spec.ts|*.md"

echo "Scanning ${SCAN_PATHS} for hardcoded secrets..."

PATTERNS=(
  # Generic high-entropy tokens
  'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}'     # JWT-like
  '[A-Za-z0-9+/]{40,}={0,2}'                         # base64 blobs (long)
  # Cloudflare specific
  'CF_API_TOKEN\s*=\s*["\x27][A-Za-z0-9_-]{30,}'
  'CF_API_KEY\s*=\s*["\x27][0-9a-f]{37}'
  # AWS creds that sometimes leak into CF Workers
  'AKIA[0-9A-Z]{16}'
  # Generic password assignments
  'password\s*=\s*["\x27][^"'\'']{8,}'
)

FOUND=0
for pattern in "${PATTERNS[@]}"; do
  results=$(grep -rEn --include="*.ts" --include="*.js" \
    --exclude-dir=node_modules --exclude-dir=dist \
    "${pattern}" "${SCAN_PATHS}" 2>/dev/null || true)

  if [[ -n "$results" ]]; then
    echo "FOUND potential hardcoded secret matching pattern: ${pattern}"
    echo "$results"
    FOUND=1
  fi
done

if (( FOUND )); then
  echo ""
  echo "ERROR: Hardcoded secrets detected. Remove them and use wrangler secret put instead." >&2
  exit 1
fi

echo "No hardcoded secrets found."
```

## GitHub Actions Workflow

```yaml
# .github/workflows/secrets-audit.yml
name: Pre-Deploy Secrets Audit

on:
  push:
    branches: [main, staging]
  pull_request:
    branches: [main, staging]

jobs:
  secrets-audit:
    name: Audit Worker secrets
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write

    strategy:
      matrix:
        environment: [staging, production]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci

      - name: Scan for hardcoded secrets in source
        run: bash scripts/scan-hardcoded-secrets.sh
        env:
          SCAN_PATHS: src/

      - name: Parse required secrets from wrangler.toml
        run: npx tsx scripts/parse-required-secrets.ts ${{ matrix.environment }}

      - name: Fetch remote secrets from Cloudflare
        run: npx tsx scripts/fetch-remote-secrets.ts ${{ matrix.environment }}
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          WORKER_NAME: ${{ vars.WORKER_NAME }}

      - name: Run secrets diff audit
        run: npx tsx scripts/audit-secrets.ts

      - name: Post audit report on PR
        if: github.event_name == 'pull_request'
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          path: dist/secrets-audit-report.md
          header: secrets-audit-${{ matrix.environment }}

      - name: Upload audit artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: secrets-audit-${{ matrix.environment }}
          path: dist/secrets-audit-report.md
          retention-days: 14

  deploy:
    name: Deploy Worker
    needs: secrets-audit
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Anti-patterns
- Fetching secret values (not just names) over the network or logging them to CI output — the Cloudflare API intentionally does not return values; never try to work around this.
- Using `wrangler secret list` in CI without a machine token scoped to read-only — a leaked CI token with write permissions on secrets is a high-severity finding.
- Treating stale secrets as safe to ignore — stale secrets may reference decommissioned credentials that still have live API access.
- Running the hardcoded scan only on changed files — rotate logic catches patterns added in older commits only when a full scan is run.
- Blocking the entire deploy on stale-secret warnings — stale secrets don't break the deploy; only missing required secrets should fail CI.

## Gotchas
- Wrangler environments (`[env.production]`) deploy the Worker under a name like `worker-name-production` not `worker-name`; the secrets API path uses that mangled name.
- The `[secrets]` top-level key in `wrangler.toml` is a Wrangler 3.x feature; earlier configs may use inline `var` comments as documentation which the parser won't pick up.
- `CF_API_TOKEN` permissions required: `Workers Scripts:Read` and `Workers KV Storage:Read` — do not grant `Edit` to a read-only audit token.
- The regex-based hardcoded secret scan produces false positives on hashed values or long base64 test fixtures; add a `.secrets-scan-ignore` pattern file as needed.
- First-time deploys have no remote secrets (404 response); the audit must treat this as "zero present" rather than an error.

## Verification
1. Remove a required secret from the Cloudflare dashboard for a staging Worker and confirm CI blocks with a missing-secret report.
2. Add `const token = "<redacted-secret>"` to a source file and confirm the hardcoded-scan step fails and catches it.
3. Rename a secret in `wrangler.toml` without updating the remote; confirm the audit shows the old name as stale and the new name as missing.
4. After running `wrangler secret put RENAMED_SECRET`, re-trigger the workflow and confirm the audit passes.
5. Verify the PR comment includes both "Present" and "Stale" sections when applicable.

## Related
- `wrangler-bulk-secrets-deploy-automation.md`
- `secrets-management-wrangler-vault.md`
- `secrets-rotation-deploy-coordination.md`
- `wrangler-config-validation-pre-deploy-ci-hook.md`
- `gitops-secrets-management.md`

## Sources
- https://developers.cloudflare.com/workers/wrangler/commands/#secret
- https://developers.cloudflare.com/api/operations/worker-script-list-secrets
- https://developers.cloudflare.com/workers/configuration/secrets/
