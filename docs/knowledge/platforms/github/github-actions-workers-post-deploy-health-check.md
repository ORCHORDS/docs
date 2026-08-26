# Post-Deploy Health Check in GitHub Actions for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker deploys successfully from the Wrangler CLI perspective (exit code 0), but the live URL returns 500 errors, fails to route correctly, or sits behind a propagation delay. Without an automated health check step, the failure is only discovered when users report it — often minutes or hours later.

## Context

Cloudflare Workers deploy propagates globally within seconds, but the edge nearest the CI runner may lag by 5–15 seconds. A naive `curl` immediately after `wrangler deploy` can return stale responses. The solution is a retry loop with exponential back-off that fails the workflow and optionally triggers a rollback when the health check never passes within a time budget.

---

## Section 1: Wrangler Deploy Step

```yaml
# .github/workflows/deploy.yml
name: Deploy Worker

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write   # required for OIDC Cloudflare auth

env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

jobs:
  deploy:
    runs-on: ubuntu-latest
    outputs:
      worker_url: ${{ steps.deploy.outputs.worker_url }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      - name: Deploy Worker
        id: deploy
        run: |
          OUTPUT=$(npx wrangler deploy --env production 2>&1)
          echo "$OUTPUT"
          # Extract the deployed URL from wrangler output
          URL=$(echo "$OUTPUT" | grep -oP 'https://[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev' | head -1)
          if [ -z "$URL" ]; then
            echo "::error::Could not parse Worker URL from wrangler output"
            exit 1
          fi
          echo "worker_url=$URL" >> "$GITHUB_OUTPUT"
          echo "Deployed to: $URL"
```

## Section 2: Health Check with Retry Loop

```bash
#!/usr/bin/env bash
# scripts/health-check.sh
# Usage: ./health-check.sh <url> [max_attempts] [sleep_seconds]

set -euo pipefail

URL="${1:?URL required}"
MAX_ATTEMPTS="${2:-12}"
SLEEP_SEC="${3:-5}"
HEALTH_PATH="${HEALTH_PATH:-/health}"
EXPECTED_STATUS="${EXPECTED_STATUS:-200}"
EXPECTED_BODY_PATTERN="${EXPECTED_BODY_PATTERN:-ok}"

attempt=0

while [ "$attempt" -lt "$MAX_ATTEMPTS" ]; do
  attempt=$((attempt + 1))
  echo "[health-check] Attempt $attempt/$MAX_ATTEMPTS → ${URL}${HEALTH_PATH}"

  HTTP_CODE=$(curl \
    --silent \
    --output /tmp/health_body \
    --write-out "%{http_code}" \
    --max-time 10 \
    --retry 0 \
    "${URL}${HEALTH_PATH}" || echo "000")

  BODY=$(cat /tmp/health_body 2>/dev/null || echo "")

  echo "[health-check] HTTP $HTTP_CODE"
  echo "[health-check] Body: ${BODY:0:200}"

  if [ "$HTTP_CODE" = "$EXPECTED_STATUS" ] && echo "$BODY" | grep -qi "$EXPECTED_BODY_PATTERN"; then
    echo "[health-check] PASSED on attempt $attempt"
    exit 0
  fi

  if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
    BACKOFF=$(( SLEEP_SEC * attempt ))
    echo "[health-check] Not healthy yet. Sleeping ${BACKOFF}s before retry..."
    sleep "$BACKOFF"
  fi
done

echo "[health-check] FAILED after $MAX_ATTEMPTS attempts"
exit 1
```

## Section 3: Full Workflow with Rollback

```yaml
  health-check:
    runs-on: ubuntu-latest
    needs: deploy
    env:
      WORKER_URL: ${{ needs.deploy.outputs.worker_url }}

    steps:
      - uses: actions/checkout@v4

      - name: Run smoke test
        id: smoke
        run: |
          chmod +x scripts/health-check.sh
          HEALTH_PATH="/health" \
          EXPECTED_STATUS="200" \
          EXPECTED_BODY_PATTERN="\"status\":\"ok\"" \
          ./scripts/health-check.sh "$WORKER_URL" 12 5
        continue-on-error: true

      - name: Rollback on failure
        if: steps.smoke.outcome == 'failure'
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          echo "::error::Health check failed — initiating rollback"
          # Roll back to previous deployment via Cloudflare API
          WORKER_NAME=$(npx wrangler whoami 2>/dev/null | grep 'Worker:' | awk '{print $2}' || echo "my-worker")
          # List deployments and get the previous one
          PREV_DEPLOYMENT=$(curl -s \
            -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
            "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/deployments" \
            | jq -r '.result.deployments[1].id // empty')

          if [ -n "$PREV_DEPLOYMENT" ]; then
            echo "Rolling back to deployment: $PREV_DEPLOYMENT"
            curl -s -X POST \
              -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
              -H "Content-Type: application/json" \
              -d "{\"id\": \"$PREV_DEPLOYMENT\"}" \
              "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/deployments"
            echo "Rollback submitted"
          else
            echo "::warning::No previous deployment found to roll back to"
          fi

      - name: Fail workflow after rollback
        if: steps.smoke.outcome == 'failure'
        run: exit 1

      - name: Notify success
        if: steps.smoke.outcome == 'success'
        run: |
          echo "::notice::Worker at $WORKER_URL is healthy"
```

## Section 4: Worker Health Endpoint (TypeScript)

```typescript
// src/index.ts
import { Env } from './types';

interface HealthResponse {
  status: 'ok' | 'degraded';
  version: string;
  timestamp: string;
  checks: Record<string, boolean>;
}

async function handleHealth(env: Env): Promise<Response> {
  const checks: Record<string, boolean> = {};

  // Check D1 connectivity
  try {
    await env.DB.prepare('SELECT 1').first();
    checks.db = true;
  } catch {
    checks.db = false;
  }

  // Check KV connectivity
  try {
    await env.KV.get('__health_probe__');
    checks.kv = true;
  } catch {
    checks.kv = false;
  }

  const allHealthy = Object.values(checks).every(Boolean);
  const body: HealthResponse = {
    status: allHealthy ? 'ok' : 'degraded',
    version: env.DEPLOY_VERSION ?? 'unknown',
    timestamp: new Date().toISOString(),
    checks,
  };

  return new Response(JSON.stringify(body), {
    status: allHealthy ? 200 : 503,
    headers: { 'Content-Type': 'application/json' },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/health') return handleHealth(env);
    return new Response('Not Found', { status: 404 });
  },
};
```

## Anti-patterns

- **Checking immediately after deploy**: Propagation takes 5–15 s. Add at least one sleep or use a retry loop.
- **Only checking HTTP status**: A 200 from a cached edge does not mean the new code is live. Include a version header or `deploy_sha` in the response body.
- **Swallowing rollback errors**: If the rollback API call itself fails, the workflow should still exit non-zero so on-call is paged.
- **Hardcoding the Worker URL**: Parse it from `wrangler deploy` output or read it from `wrangler.toml` to keep the workflow environment-agnostic.

## Gotchas

- `wrangler deploy` exits 0 even if the upload succeeded but a global dispatch failure occurred. Always verify the live URL.
- The Cloudflare Deployments API (`/deployments`) requires the `Workers Scripts: Edit` token permission scope.
- `continue-on-error: true` on the smoke step is required so the rollback step can run; the final explicit `exit 1` step re-fails the job for GitHub's status checks.
- Workers behind a Custom Domain (not `*.workers.dev`) may need additional DNS warm-up time before the health check URL resolves.

## Verification

```bash
# Local dry-run against a deployed Worker
HEALTH_PATH=/health \
EXPECTED_STATUS=200 \
EXPECTED_BODY_PATTERN='"status":"ok"' \
./scripts/health-check.sh https://my-worker.example.workers.dev 3 2
```

Expected output:
```
[health-check] Attempt 1/3 → https://my-worker.example.workers.dev/health
[health-check] HTTP 200
[health-check] Body: {"status":"ok","version":"abc123",...}
[health-check] PASSED on attempt 1
```

## Related

- `documentation/docs/policies/github/github-actions-monorepo-affected-packages-deploy.md`
- `documentation/docs/policies/github/github-actions-d1-backup-pre-migration.md`
- `documentation/workers/workers-graceful-error-responses.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/api/operations/worker-deployments-list-deployments
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/using-jobs-in-a-workflow
