# Workers Secrets Bulk Rotation Automation CI

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Workers application accumulates secrets over time — API keys, HMAC
signing keys, database connection tokens, and third-party OAuth credentials. When
a security incident, key expiry policy, or vendor rotation event requires rotating
multiple secrets simultaneously, doing so manually through the Cloudflare dashboard
is slow, error-prone, and produces no audit trail. For example project / example.com,
a compromised signing key for anonymous post tokens must be rotated across all
Worker environments within minutes with zero downtime.

## Context

Wrangler's `secret bulk` command accepts a JSON file of key-value pairs and
atomically pushes all secrets in a single API call per Worker environment. This
makes it suitable for CI-driven bulk rotation: secrets are stored in a vault
(GitHub Actions secrets, HashiCorp Vault, or AWS Secrets Manager), fetched at
rotation time, and pushed to Cloudflare via an automated pipeline. The Worker
continues serving traffic during the push — secrets take effect on the next
request isolation boundary, typically within seconds.

## Section 1 — secrets inventory and naming convention

Maintain a canonical list of all Worker secrets in a non-secret manifest file.
This file declares the expected secret names and which environments they apply to,
without storing the values.

```json
// config/secrets-manifest.json
{
  "worker": "example project-api",
  "environments": ["production", "staging"],
  "secrets": [
    {
      "name": "ANON_POST_HMAC_KEY",
      "description": "HMAC-SHA256 key for anonymous post ID signing",
      "rotation_days": 90,
      "critical": true
    },
    {
      "name": "SESSION_ENCRYPTION_KEY",
      "description": "AES-256-GCM key for session token encryption",
      "rotation_days": 90,
      "critical": true
    },
    {
      "name": "MODERATION_WEBHOOK_SECRET",
      "description": "Shared secret for moderation service webhook auth",
      "rotation_days": 180,
      "critical": false
    },
    {
      "name": "CLOUDFLARE_ANALYTICS_TOKEN",
      "description": "Analytics Engine write token",
      "rotation_days": 365,
      "critical": false
    }
  ]
}
```

Generate the bulk secrets JSON at rotation time from the vault — never commit
secret values:

```bash
# scripts/generate-bulk-secrets.sh
#!/usr/bin/env bash
set -euo pipefail

# Fetch secrets from GitHub Actions environment or vault
# In CI, these are set as masked environment variables
cat > /tmp/bulk-secrets.json <<EOF
{
  "ANON_POST_HMAC_KEY": "${ANON_POST_HMAC_KEY:?}",
  "SESSION_ENCRYPTION_KEY": "${SESSION_ENCRYPTION_KEY:?}",
  "MODERATION_WEBHOOK_SECRET": "${MODERATION_WEBHOOK_SECRET:?}",
  "CLOUDFLARE_ANALYTICS_TOKEN": "${CLOUDFLARE_ANALYTICS_TOKEN:?}"
}
EOF

echo "Bulk secrets file generated (values masked in logs)."
```

## Section 2 — bulk rotation workflow

The rotation workflow uses `wrangler secret bulk` with the generated JSON and
rotates staging before production. Staging confirmation is a required step before
production proceeds.

```yaml
# .github/workflows/rotate-secrets.yml
name: Bulk Secrets Rotation

on:
  workflow_dispatch:
    inputs:
      environment:
        description: "Target environment (staging / production / all)"
        required: true
        default: "staging"
        type: choice
        options: [staging, production, all]
      reason:
        description: "Rotation reason for audit log"
        required: true
        type: string

jobs:
  rotate-staging:
    name: Rotate staging secrets
    runs-on: ubuntu-latest
    if: >
      github.event.inputs.environment == 'staging' ||
      github.event.inputs.environment == 'all'
    environment: staging-secrets
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci

      - name: Generate bulk secrets JSON
        env:
          ANON_POST_HMAC_KEY: ${{ secrets.STAGING_ANON_POST_HMAC_KEY }}
          SESSION_ENCRYPTION_KEY: ${{ secrets.STAGING_SESSION_ENCRYPTION_KEY }}
          MODERATION_WEBHOOK_SECRET: ${{ secrets.STAGING_MODERATION_WEBHOOK_SECRET }}
          CLOUDFLARE_ANALYTICS_TOKEN: ${{ secrets.STAGING_CLOUDFLARE_ANALYTICS_TOKEN }}
        run: bash scripts/generate-bulk-secrets.sh

      - name: Rotate secrets (staging)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx wrangler secret bulk /tmp/bulk-secrets.json \
            --name example project-api \
            --env staging
          echo "Staging secrets rotated at $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            >> "$GITHUB_STEP_SUMMARY"

      - name: Cleanup secret file
        if: always()
        run: rm -f /tmp/bulk-secrets.json

  confirm-staging:
    name: Confirm staging health before production
    needs: rotate-staging
    runs-on: ubuntu-latest
    if: github.event.inputs.environment == 'all'
    steps:
      - name: Smoke test staging endpoint
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            https://staging.example.com/api/health)
          if [ "$STATUS" != "200" ]; then
            echo "ERROR: Staging health check failed (HTTP $STATUS)" && exit 1
          fi
          echo "Staging health OK — proceeding to production rotation."

  rotate-production:
    name: Rotate production secrets
    needs: [confirm-staging]
    runs-on: ubuntu-latest
    if: >
      github.event.inputs.environment == 'production' ||
      github.event.inputs.environment == 'all'
    environment: production-secrets
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci

      - name: Generate production bulk secrets JSON
        env:
          ANON_POST_HMAC_KEY: ${{ secrets.PROD_ANON_POST_HMAC_KEY }}
          SESSION_ENCRYPTION_KEY: ${{ secrets.PROD_SESSION_ENCRYPTION_KEY }}
          MODERATION_WEBHOOK_SECRET: ${{ secrets.PROD_MODERATION_WEBHOOK_SECRET }}
          CLOUDFLARE_ANALYTICS_TOKEN: ${{ secrets.PROD_CLOUDFLARE_ANALYTICS_TOKEN }}
        run: bash scripts/generate-bulk-secrets.sh

      - name: Rotate secrets (production)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx wrangler secret bulk /tmp/bulk-secrets.json \
            --name example project-api \
            --env production

      - name: Cleanup and audit log
        if: always()
        run: |
          rm -f /tmp/bulk-secrets.json
          echo "## Production Secrets Rotation" >> "$GITHUB_STEP_SUMMARY"
          echo "- **Time:** $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_STEP_SUMMARY"
          echo "- **Triggered by:** ${{ github.actor }}" >> "$GITHUB_STEP_SUMMARY"
          echo "- **Reason:** ${{ github.event.inputs.reason }}" >> "$GITHUB_STEP_SUMMARY"
```

## Section 3 — dual-key rotation for zero downtime (HMAC key transition)

Rotating signing keys without a grace period invalidates all outstanding anonymous
post tokens immediately. Use a dual-key pattern: keep both the old and new HMAC key
active during the transition window.

```typescript
// src/lib/hmac-rotation.ts
const PRIMARY_KEY = env.ANON_POST_HMAC_KEY;
const PREVIOUS_KEY = env.ANON_POST_HMAC_KEY_PREV; // set during grace period only

export async function verifyPostToken(token: string, id: string): Promise<boolean> {
  const keys = [PRIMARY_KEY, PREVIOUS_KEY].filter(Boolean);

  for (const keyMaterial of keys) {
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(keyMaterial),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"]
    );

    const [data, sigHex] = token.split(".");
    const sig = hexToBytes(sigHex);
    const valid = await crypto.subtle.verify("HMAC", key, sig, new TextEncoder().encode(data));

    if (valid) return true;
  }

  return false;
}

function hexToBytes(hex: string): Uint8Array {
  return new Uint8Array(hex.match(/../g)!.map((b) => parseInt(b, 16)));
}
```

During rotation: push new primary, set old key as `ANON_POST_HMAC_KEY_PREV`. After
grace period (e.g. 24h), remove `_PREV` in a follow-up bulk push.

## Section 4 — rollback

Wrangler does not version secrets — once pushed, the old value is gone. Maintain
a secure backup of the previous secret values in the vault before rotation:

```bash
# Before rotation: snapshot current production secrets to vault
# (Cloudflare does not expose secret values via API — must come from the vault)

# If the new key causes failures, re-push the previous values immediately:
cat > /tmp/rollback-secrets.json <<EOF
{
  "ANON_POST_HMAC_KEY": "${PREVIOUS_ANON_POST_HMAC_KEY:?}"
}
EOF

npx wrangler secret bulk /tmp/rollback-secrets.json \
  --name example project-api \
  --env production

rm -f /tmp/rollback-secrets.json
echo "Rollback complete — previous HMAC key restored."
```

Always test the rollback procedure in staging before executing a production rotation.

## Anti-patterns

- Rotating secrets directly via the Cloudflare dashboard — no audit trail, no
  automation, prone to manual errors
- Storing secret values in the repository even temporarily in a `.env` file that
  gets committed
- Using a single HMAC key without a dual-key grace period — causes instant
  token invalidation for all active anonymous sessions
- Rotating production before validating staging — eliminates the safety net
- Not generating new cryptographically random values for each rotation (e.g.
  reusing old key material)

## Gotchas

- `wrangler secret bulk` replaces only the secrets listed in the JSON file — other
  existing secrets are untouched. This is safe for partial rotations.
- The `--env` flag must match the environment name in `wrangler.toml` exactly.
- Secrets pushed to a Worker take effect on new isolate cold starts; long-lived
  isolates may serve one or two requests with the old key before the new value
  propagates — the dual-key pattern handles this.
- GitHub Actions masked secrets are redacted in logs but not in `$GITHUB_STEP_SUMMARY`
  — never echo secret values into the summary.

## Verification

1. Trigger the workflow with `environment: staging` — verify the wrangler output
   shows all expected secret names without values.
2. Make a request to the staging API with a token signed by the new key — it should
   succeed.
3. Make a request with a token signed by the old key during the grace period — it
   should still succeed via the `_PREV` fallback.
4. After the grace period, remove `_PREV` and verify old tokens are now rejected.
5. Check the GitHub Actions summary for the audit log entry.

## Related

- `/documentation/categories/deploy/wrangler-bulk-secrets-deploy-automation.md`
- `/documentation/categories/deploy/workers-secrets-rotation-zero-downtime.md`
- `/documentation/categories/deploy/wrangler-ci-secrets-audit-pre-deploy-scan.md`
- `/documentation/categories/deploy/secrets-management-wrangler-vault.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#secret-bulk
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions
