# Wrangler Secrets Per-Environment Workflow

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Developers accidentally push a staging secret to production, or can't tell which secret value is active in which Wrangler environment.
A disciplined per-environment secrets workflow prevents cross-contamination and makes secret rotation auditable.

## Context
Wrangler environments (`[env.staging]`, `[env.production]`) are independent Workers deployments that share a `wrangler.toml` but own separate secret namespaces in the Cloudflare dashboard.
`wrangler secret put` is environment-scoped: the `--env` flag determines which deployment receives the value.
In monorepos with git worktrees, each feature branch may run against its own preview environment, making it essential to bind secrets precisely to the right environment slot.

---

## Setup — Environment Inventory File

Maintain a non-secret inventory that maps environment names to expected secret keys.
This file lives in the repo; actual values live in GitHub Actions secrets or 1Password:

```toml
# wrangler.toml (excerpt)
name = "my-api"
compatibility_date = "2026-07-01"

[env.preview]
name = "my-api-preview"

[env.staging]
name = "my-api-staging"

[env.production]
name = "my-api-production"
```

```typescript
// config/secrets-manifest.ts
export const SECRETS_MANIFEST: Record<string, string[]> = {
  preview: [
    'DATABASE_URL',
    'JWT_SECRET',
    'THIRD_PARTY_API_KEY',
  ],
  staging: [
    'DATABASE_URL',
    'JWT_SECRET',
    'THIRD_PARTY_API_KEY',
    'STRIPE_SECRET_KEY',
  ],
  production: [
    'DATABASE_URL',
    'JWT_SECRET',
    'THIRD_PARTY_API_KEY',
    'STRIPE_SECRET_KEY',
    'SENTRY_DSN',
  ],
};
```

---

## Section 1 — Bulk-Upload Secrets Per Environment

Use `wrangler secret bulk` with a per-environment `.env` file generated from your secrets store.
Never commit the `.env` files; generate them at CI runtime:

```bash
#!/usr/bin/env bash
# scripts/push-secrets.sh <environment>
set -euo pipefail

ENV="${1:?Usage: $0 <preview|staging|production>}"
WORKER_DIR="${2:-.}"

echo "Pushing secrets for environment: $ENV"

# Generate a temp JSON file from environment variables
# (Variables are injected by GitHub Actions secrets or op run)
tmpfile=$(mktemp /tmp/secrets-XXXXXX.json)
trap 'rm -f "$tmpfile"' EXIT

tsx scripts/build-secrets-json.ts "$ENV" > "$tmpfile"

cd "$WORKER_DIR"
npx wrangler secret bulk "$tmpfile" --env "$ENV"
echo "Done — secrets pushed to $ENV"
```

```typescript
// scripts/build-secrets-json.ts
// Reads env vars (set by CI) and outputs a JSON object for wrangler secret bulk
import { SECRETS_MANIFEST } from '../config/secrets-manifest';

const env = process.argv[2];
if (!env || !SECRETS_MANIFEST[env]) {
  console.error(`Unknown environment: ${env}`);
  process.exit(1);
}

const keys = SECRETS_MANIFEST[env];
const result: Record<string, string> = {};

for (const key of keys) {
  const value = process.env[key];
  if (!value) {
    console.error(`Missing env var: ${key} (required for ${env})`);
    process.exit(1);
  }
  result[key] = value;
}

process.stdout.write(JSON.stringify(result, null, 2));
```

---

## Section 2 — GitHub Actions: Per-Environment Secret Push

Each environment uses a separate job with scoped GitHub environment secrets, preventing cross-environment leakage:

```yaml
# .github/workflows/push-secrets.yml
name: Push Wrangler Secrets

on:
  workflow_dispatch:
    inputs:
      environment:
        description: Target environment
        required: true
        type: choice
        options: [preview, staging, production]
      worker:
        description: Worker package path
        required: false
        default: packages/api-worker

jobs:
  push-secrets:
    runs-on: ubuntu-latest
    # GitHub environment gates approval for production
    environment: ${{ inputs.environment }}
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Push secrets to ${{ inputs.environment }}
        working-directory: ${{ inputs.worker }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          JWT_SECRET: ${{ secrets.JWT_SECRET }}
          THIRD_PARTY_API_KEY: ${{ secrets.THIRD_PARTY_API_KEY }}
          STRIPE_SECRET_KEY: ${{ secrets.STRIPE_SECRET_KEY }}
          SENTRY_DSN: ${{ secrets.SENTRY_DSN }}
        run: |
          bash ../../scripts/push-secrets.sh ${{ inputs.environment }} .
```

---

## Section 3 — Audit: Verify Deployed Secret Keys Match Manifest

After a push, verify the live secret list matches the manifest.
Note: Wrangler only returns secret *names*, never values:

```typescript
// scripts/audit-secrets.ts
import { execSync } from 'node:child_process';
import { SECRETS_MANIFEST } from '../config/secrets-manifest';

const env = process.argv[2];
if (!env || !SECRETS_MANIFEST[env]) {
  console.error(`Unknown environment: ${env}`);
  process.exit(1);
}

const expected = new Set(SECRETS_MANIFEST[env]);

// wrangler secret list outputs JSON array of {name, type}
const raw = execSync(`npx wrangler secret list --env ${env} --json`, {
  cwd: process.argv[3] ?? '.',
  encoding: 'utf8',
});

const deployed: Array<{ name: string; type: string }> = JSON.parse(raw);
const deployedNames = new Set(deployed.map(s => s.name));

const missing = [...expected].filter(k => !deployedNames.has(k));
const extra = [...deployedNames].filter(k => !expected.has(k));

if (missing.length) {
  console.error('MISSING secrets (expected but not deployed):');
  missing.forEach(k => console.error(` - ${k}`));
}
if (extra.length) {
  console.warn('EXTRA secrets (deployed but not in manifest):');
  extra.forEach(k => console.warn(` + ${k}`));
}

if (missing.length) process.exit(1);
console.log(`Audit passed for ${env}: ${deployedNames.size} secrets deployed`);
```

---

## Anti-patterns

- Using `wrangler secret put` interactively without `--env` — defaults to the root environment and silently affects production
- Storing secret values in `wrangler.toml` under `[vars]` — values are plaintext in the repo and in Wrangler's deploy payload
- A single GitHub Actions secret like `ALL_SECRETS_JSON` shared across environments — bypasses GitHub environment protection rules
- Rotating a secret in one environment without auditing sibling environments — leaves the old value active where it matters most

## Gotchas

- `wrangler secret bulk` is additive: existing secrets not in the JSON payload are NOT deleted; use `wrangler secret delete` explicitly for removal
- `--env` must exactly match a named environment in `wrangler.toml`; a typo silently creates a new, unintended environment
- GitHub environment protection rules (require reviewers) only apply to jobs that declare `environment:` — a plain `env:` block at the step level does not trigger approval gates
- Preview environments created per-worktree share the same `[env.preview]` secret namespace unless you use fully unique environment names per branch

## Verification

```bash
# List current secrets for each environment (names only, no values)
npx wrangler secret list --env preview  --json | jq '.[].name'
npx wrangler secret list --env staging  --json | jq '.[].name'
npx wrangler secret list --env production --json | jq '.[].name'

# Run the audit script locally (requires CLOUDFLARE_API_TOKEN)
npx tsx scripts/audit-secrets.ts staging packages/api-worker

# Confirm a specific secret exists without revealing its value
npx wrangler secret list --env production --json | jq 'map(select(.name=="JWT_SECRET")) | length'
```

## Related

- `wrangler-secrets-bulk-management-ci.md`
- `wrangler-environments-staging-production.md`
- `wrangler-config-schema-validation-ci.md`
- `github-actions-wrangler-deploy-pipeline.md`
- `git-worktree-parallel-wrangler-environments.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#secret
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- https://developers.cloudflare.com/workers/wrangler/configuration/#environments
