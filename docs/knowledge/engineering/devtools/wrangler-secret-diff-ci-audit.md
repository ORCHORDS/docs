# Wrangler Secret List Diff: CI Audit for Secret Drift

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A Cloudflare Worker silently fails in production because a required secret was added to the source code but never uploaded to the Workers runtime, or a secret was deleted from the runtime but is still referenced in code. A CI audit that diffs the declared secrets (from source) against the live secrets (from `wrangler secret list`) catches this drift before deploy.

## Context
Cloudflare Workers secrets are uploaded out-of-band via `wrangler secret put` and live in the Workers runtime, not in version control. When a team adds a new environment variable reference in `src/` without uploading the corresponding secret, the Worker crashes at runtime with a binding error. `wrangler secret list` returns the names (never values) of all secrets currently uploaded for a Worker. Comparing this list against a manifest in source control creates a reliable drift detector that can gate merges or block deploys.

## Declaring the Secret Manifest

Keep a plain text file listing required secret names — one per line, no values. This file lives in version control and is the source of truth.

`apps/api-worker/.secrets.required`:

```
DATABASE_URL
STRIPE_SECRET_KEY
SENDGRID_API_KEY
JWT_SECRET
INTERNAL_API_KEY
```

Secrets with environment-specific variants (e.g., staging vs production) use a naming convention:

`apps/api-worker/.secrets.required`:

```
# Core secrets — required in all environments
DATABASE_URL
JWT_SECRET

# Payment processing
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET

# Email
SENDGRID_API_KEY

# Internal
INTERNAL_API_KEY
ENCRYPTION_KEY
```

Lines beginning with `#` are comments. The audit script strips them.

## Audit Script

`scripts/audit-secrets.sh`:

```bash
#!/usr/bin/env bash
# Usage: ./scripts/audit-secrets.sh <worker-name> [environment]
# Compares .secrets.required against live wrangler secret list output.
# Exits 1 if any required secrets are missing from the runtime.

set -euo pipefail

WORKER="${1:?Worker name required as first argument}"
ENV="${2:-}"
MANIFEST="${3:-.secrets.required}"

# Build the wrangler command
WRANGLER_CMD="wrangler secret list --name ${WORKER}"
if [ -n "$ENV" ]; then
  WRANGLER_CMD="${WRANGLER_CMD} --env ${ENV}"
fi

echo "=== Secret audit: ${WORKER}${ENV:+ (${ENV})} ==="

# Fetch live secrets (names only — values are never returned)
LIVE_SECRETS=$(${WRANGLER_CMD} --json 2>/dev/null \
  | jq -r '.[].name' \
  | sort)

if [ -z "$LIVE_SECRETS" ]; then
  echo "WARNING: No secrets found in runtime (or wrangler auth failed)"
fi

# Parse the manifest — strip comments and blank lines, sort
REQUIRED_SECRETS=$(grep -v '^\s*#' "${MANIFEST}" \
  | grep -v '^\s*$' \
  | sort)

# Find secrets in manifest but missing from runtime
MISSING=$(comm -23 \
  <(echo "$REQUIRED_SECRETS") \
  <(echo "$LIVE_SECRETS"))

# Find secrets in runtime but absent from manifest (informational)
EXTRA=$(comm -13 \
  <(echo "$REQUIRED_SECRETS") \
  <(echo "$LIVE_SECRETS"))

FAIL=0

if [ -n "$MISSING" ]; then
  echo ""
  echo "MISSING secrets (in manifest, not uploaded to runtime):"
  echo "$MISSING" | while read -r s; do echo "  - ${s}"; done
  FAIL=1
fi

if [ -n "$EXTRA" ]; then
  echo ""
  echo "EXTRA secrets (uploaded to runtime, not in manifest):"
  echo "$EXTRA" | while read -r s; do echo "  ? ${s}"; done
fi

if [ "$FAIL" -eq 0 ]; then
  echo ""
  echo "OK: All required secrets are present in the runtime."
else
  echo ""
  echo "FAIL: Secret drift detected. Upload missing secrets before deploying."
  exit 1
fi
```

Make it executable: `chmod +x scripts/audit-secrets.sh`

## GitHub Actions Integration

`.github/workflows/secret-audit.yml`:

```yaml
name: Secret Drift Audit

on:
  pull_request:
    paths:
      - "apps/**/.secrets.required"
      - "apps/**/src/**"
  schedule:
    # Run daily at 06:00 UTC to catch out-of-band secret deletions
    - cron: "0 6 * * *"
  workflow_dispatch:

jobs:
  audit:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - worker: api-worker
            env: production
            dir: apps/api-worker
          - worker: email-worker
            env: production
            dir: apps/email-worker
          - worker: cron-worker
            env: production
            dir: apps/cron-worker

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Audit secrets for ${{ matrix.worker }}
        run: |
          ./scripts/audit-secrets.sh \
            "${{ matrix.worker }}" \
            "${{ matrix.env }}" \
            "${{ matrix.dir }}/.secrets.required"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_AUDIT_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  notify-on-drift:
    needs: audit
    if: failure() && github.event_name == 'schedule'
    runs-on: ubuntu-latest
    steps:
      - name: Notify on secret drift
        run: |
          curl -s -X POST "${{ secrets.SLACK_WEBHOOK_URL }}" \
            -H "Content-Type: application/json" \
            -d '{
              "text": ":rotating_light: Secret drift detected in Workers. Check the audit job: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
            }'
```

## TypeScript: Enforce Secret Names in Source Code

Use a generated type to ensure every `env.SECRET_NAME` reference in TypeScript matches the manifest:

`scripts/generate-secret-types.ts`:

```typescript
import { readFileSync, writeFileSync } from "fs";
import { join } from "path";

const WORKERS = ["api-worker", "email-worker", "cron-worker"] as const;

for (const worker of WORKERS) {
  const manifestPath = join("apps", worker, ".secrets.required");
  const outPath = join("apps", worker, "src", "generated", "secret-types.d.ts");

  const manifest = readFileSync(manifestPath, "utf8");
  const secrets = manifest
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"));

  const secretFields = secrets.map((s) => `    readonly ${s}: string;`).join("\n");

  const content = `// AUTO-GENERATED — do not edit by hand
// Source: ${manifestPath}
// Regenerate: pnpm generate:secret-types

export interface WorkerSecrets {
${secretFields}
}
`;

  writeFileSync(outPath, content, "utf8");
  console.log(`Generated types for ${worker}: ${secrets.length} secrets`);
}
```

In the Worker source:

```typescript
// src/index.ts
import type { WorkerSecrets } from "./generated/secret-types";

interface Env extends WorkerSecrets {
  // Bindings (non-secret)
  DB: D1Database;
  KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // TypeScript error if SECRET_NAME is not in the manifest
    const token = env.STRIPE_SECRET_KEY;
    return new Response("ok");
  },
} satisfies ExportedHandler<Env>;
```

Add `generate:secret-types` to the root `package.json`:

```json
{
  "scripts": {
    "generate:secret-types": "tsx scripts/generate-secret-types.ts",
    "prebuild": "pnpm generate:secret-types"
  }
}
```

## Uploading Missing Secrets (Remediation)

When the audit finds drift, the remediation command:

```bash
# Upload a single missing secret interactively
wrangler secret put STRIPE_SECRET_KEY --name api-worker --env production

# Bulk upload from a .env file (values only, never commit this)
# .env.secrets.production (gitignored):
# STRIPE_SECRET_KEY=sk_live_...
# SENDGRID_API_KEY=SG....

while IFS='=' read -r key _; do
  [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
  echo "Uploading ${key}..."
  wrangler secret put "$key" --name api-worker --env production \
    < <(grep "^${key}=" .env.secrets.production | cut -d= -f2-)
done < apps/api-worker/.secrets.required
```

## Anti-patterns

- **Storing secret values in `.secrets.required`** — This file lists only secret names and lives in version control. Values must never appear here; use a gitignored `.env.secrets.*` file for values.
- **Using `CLOUDFLARE_API_TOKEN` with edit permissions for read-only audits** — The audit only calls `wrangler secret list`; create a dedicated API token with `Workers Scripts:Read` permission to minimize blast radius.
- **Skipping the audit on PRs that don't touch source files** — A PR that adds a new `.secrets.required` entry without uploading the secret will pass CI and break production. Run the audit on any change to the manifest.
- **Treating EXTRA secrets as errors** — Secrets in the runtime that are absent from the manifest may be legacy entries from old deployments; log them as warnings but do not fail on them without investigation.
- **Checking in `.env` files with real secret values** — Even `.env.secrets.production.example` is risky if a developer copies it with real values and forgets to gitignore it. Use `git-secrets` or `detect-secrets` pre-commit hooks.

## Gotchas

- `wrangler secret list` requires the `Workers Scripts:Read` (or equivalent) permission on the API token; a `Workers:Edit` token also works but gives excessive privilege to a read-only operation.
- The `--env` flag in `wrangler secret list` refers to wrangler environments (as defined in `wrangler.toml`), not Cloudflare environments in the dashboard; ensure `[env.production]` is declared in `wrangler.toml` or the flag is silently ignored.
- `wrangler secret list --json` returns an empty array `[]` both when there are no secrets AND when authentication fails silently — always check for a non-zero `wrangler` exit code separately.
- Secret names are case-sensitive on the Cloudflare side; `Database_URL` and `DATABASE_URL` are different secrets. Normalize to `UPPER_SNAKE_CASE` in the manifest and enforce it via a linter.
- On newly created Workers with no deployed version, `wrangler secret list` may return an error instead of an empty array. The audit script handles this with `|| true` but this means drift is undetected on first deploy.

## Verification

```bash
# Upload a test secret
wrangler secret put TEST_SECRET --name api-worker --env staging <<< "test-value-123"

# Add it to manifest
echo "TEST_SECRET" >> apps/api-worker/.secrets.required

# Audit should pass
./scripts/audit-secrets.sh api-worker staging apps/api-worker/.secrets.required
# Expected: "OK: All required secrets are present"

# Remove from runtime but keep in manifest
wrangler secret delete TEST_SECRET --name api-worker --env staging

# Audit should fail
./scripts/audit-secrets.sh api-worker staging apps/api-worker/.secrets.required
# Expected: "MISSING secrets: TEST_SECRET" + exit 1

# Clean up
sed -i '/^TEST_SECRET$/d' apps/api-worker/.secrets.required
```

## Related
- `wrangler-secret-bulk-import-script.md`
- `wrangler-config-validation-ci.md`
- `wrangler-dev-local-d1-r2-kv.md`
- `wrangler-tail-log-streaming-production.md`
- `typescript-cloudflare-workers-strict.md`

## Sources
- https://developers.cloudflare.com/workers/wrangler/commands/#secret
- https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- https://developers.cloudflare.com/workers/configuration/secrets/
