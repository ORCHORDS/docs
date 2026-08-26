# GitOps Automated Deployment from main Branch Pushes via GitHub Actions

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Every merge to `main` should automatically deploy the Cloudflare Worker to production, run a
health check, and roll back if the health check fails — all without manual `wrangler deploy`
invocations. The workflow must support multiple environments (staging, production), report deploy
status to Slack or GitHub, and be resilient to transient Cloudflare API errors.

---

## Context

GitOps treats the Git repository as the single source of truth for deployed state. A push to
`main` is the deployment event; the CI pipeline is the deployment agent. Cloudflare Workers
supports this model natively:

- `wrangler deploy` is idempotent and atomic — it either succeeds or leaves the previous version
  in place.
- Wrangler reads `CLOUDFLARE_API_TOKEN` from the environment, enabling secret injection via CI.
- Cloudflare's `wrangler rollback` command reverts to the previous deployment without a new
  build.
- Worker health can be verified immediately after deploy via a dedicated `/health` endpoint.

---

## Solution

### 1. Repository secrets setup

In GitHub repository Settings > Secrets and variables > Actions, add:

| Secret name | Value |
|-------------|-------|
| `CLOUDFLARE_API_TOKEN` | API token with `Workers Scripts:Edit` permission |
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare account ID |
| `SLACK_WEBHOOK_URL` | (Optional) Incoming webhook for deploy notifications |

### 2. Per-environment wrangler.toml

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-08-01"

[env.staging]
name = "my-worker-staging"
vars = { ENVIRONMENT = "staging" }

[env.production]
name = "my-worker-production"
vars = { ENVIRONMENT = "production" }
```

### 3. Main GitHub Actions workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy Workers

on:
  push:
    branches:
      - main

concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: false   # never cancel an in-progress deploy

jobs:
  deploy:
    name: Deploy to ${{ matrix.environment }}
    runs-on: ubuntu-latest
    permissions:
      contents: read
      deployments: write
    strategy:
      matrix:
        include:
          - environment: staging
            health_url: https://my-worker-staging.example.workers.dev/health
            requires_approval: false
          - environment: production
            health_url: https://my-worker-production.example.workers.dev/health
            requires_approval: true
      fail-fast: false

    environment:
      name: ${{ matrix.environment }}
      url: ${{ matrix.health_url }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npm run build --if-present

      - name: Deploy to ${{ matrix.environment }}
        id: deploy
        run: |
          npx wrangler deploy --env ${{ matrix.environment }} 2>&1 | tee deploy-output.txt
          DEPLOY_VERSION=$(grep -oP 'Version ID: \K[a-f0-9-]+' deploy-output.txt || echo 'unknown')
          echo "version_id=${DEPLOY_VERSION}" >> "$GITHUB_OUTPUT"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Health check
        id: health
        run: |
          HEALTH_URL="${{ matrix.health_url }}"
          MAX_ATTEMPTS=10
          SLEEP_SECONDS=6

          for i in $(seq 1 $MAX_ATTEMPTS); do
            STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
            echo "[health] attempt ${i}/${MAX_ATTEMPTS} — HTTP ${STATUS}"
            if [ "$STATUS" = "200" ]; then
              echo "healthy=true" >> "$GITHUB_OUTPUT"
              exit 0
            fi
            sleep $SLEEP_SECONDS
          done

          echo "healthy=false" >> "$GITHUB_OUTPUT"
          exit 1

      - name: Rollback on health check failure
        if: failure() && steps.deploy.outcome == 'success' && steps.health.outcome == 'failure'
        run: |
          echo "[rollback] health check failed — rolling back ${{ matrix.environment }}"
          npx wrangler rollback --env ${{ matrix.environment }} --message "auto-rollback: health check failed after ${{ github.sha }}"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Notify Slack
        if: always() && env.SLACK_WEBHOOK_URL != ''
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: |
          OUTCOME="${{ job.status }}"
          COLOR=$([ "$OUTCOME" = "success" ] && echo "#36a64f" || echo "#d9534f")
          ICON=$([ "$OUTCOME" = "success" ] && echo ":white_check_mark:" || echo ":rotating_light:")
          curl -sf -X POST "$SLACK_WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "$(jq -n \
              --arg color "$COLOR" \
              --arg icon "$ICON" \
              --arg env "${{ matrix.environment }}" \
              --arg sha "${{ github.sha }}" \
              --arg actor "${{ github.actor }}" \
              --arg outcome "$OUTCOME" \
              --arg run_url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" \
              '{attachments:[{color:$color,text:"\($icon) Workers deploy to \($env): \($outcome)\nCommit: \($sha[0:8]) by \($actor)\n<\($run_url)|View run>"}]}')"
```

### 4. TypeScript deploy health checker

For a more sophisticated health check that validates the response body:

```typescript
// scripts/health-check.ts
const HEALTH_URL = process.env.HEALTH_URL ?? '';
const MAX_ATTEMPTS = parseInt(process.env.MAX_ATTEMPTS ?? '10', 10);
const SLEEP_MS = parseInt(process.env.SLEEP_MS ?? '6000', 10);

interface HealthResponse {
  status: 'ok' | 'degraded' | 'error';
  version: string;
  timestamp: string;
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function checkHealth(): Promise<boolean> {
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      const res = await fetch(HEALTH_URL, {
        signal: AbortSignal.timeout(5_000),
      });

      if (!res.ok) {
        console.log(`[health] attempt ${attempt}/${MAX_ATTEMPTS} — HTTP ${res.status}`);
        await sleep(SLEEP_MS);
        continue;
      }

      const body = (await res.json()) as HealthResponse;
      console.log(`[health] attempt ${attempt}/${MAX_ATTEMPTS} — status: ${body.status}, version: ${body.version}`);

      if (body.status === 'ok') return true;
    } catch (err) {
      console.log(`[health] attempt ${attempt}/${MAX_ATTEMPTS} — error: ${(err as Error).message}`);
    }

    if (attempt < MAX_ATTEMPTS) await sleep(SLEEP_MS);
  }

  return false;
}

(async () => {
  const healthy = await checkHealth();
  if (!healthy) {
    console.error('[health] FAILED — Worker did not become healthy in time');
    process.exit(1);
  }
  console.log('[health] OK');
})();
```

Use it in the workflow:

```yaml
- name: Health check (advanced)
  run: npx ts-node scripts/health-check.ts
  env:
    HEALTH_URL: ${{ matrix.health_url }}
    MAX_ATTEMPTS: '10'
    SLEEP_MS: '6000'
```

### 5. Automatic rollback implementation detail

```typescript
// scripts/rollback.ts
import { execSync } from 'node:child_process';

const environment = process.env.DEPLOY_ENV ?? 'production';
const commitSha = process.env.GITHUB_SHA ?? 'unknown';
const message = `auto-rollback: health check failed after ${commitSha.slice(0, 8)}`;

console.log(`[rollback] initiating rollback for environment: ${environment}`);
console.log(`[rollback] reason: ${message}`);

try {
  execSync(
    `npx wrangler rollback --env ${environment} --message "${message}"`,
    { stdio: 'inherit' },
  );
  console.log('[rollback] rollback completed successfully');
} catch (err) {
  console.error('[rollback] rollback failed:', (err as Error).message);
  process.exit(1);
}
```

---

## Implementation Details

### concurrency group strategy

The `concurrency` block with `cancel-in-progress: false` ensures that if two pushes land in
quick succession, the second deploy waits for the first to complete rather than running in
parallel. This prevents race conditions where two deploys arrive at Cloudflare out of order.

### Deploy version capture

Wrangler prints the deployed version ID in its output:

```
Deployed my-worker triggers:
  Version ID: 3f2a1b4c-...
```

Capturing this in `$GITHUB_OUTPUT` lets downstream steps or notifications reference the exact
version that was deployed.

### GitHub Environments for approval gates

Setting `requires_approval: true` in the matrix combined with a GitHub Environment protection
rule creates a mandatory approval gate before the production job starts. Configure this in
Repository Settings > Environments > production > Required reviewers.

### Rate limit handling

If deploying many Workers in parallel hits Cloudflare's API rate limits, add retry logic:

```bash
for attempt in 1 2 3; do
  npx wrangler deploy --env "$ENV" && break
  echo "[deploy] attempt ${attempt} failed, retrying..."
  sleep $((attempt * 10))
done
```

---

## Anti-patterns

- **Deploying from feature branches.** Only `main` (or an explicit release branch) should trigger
  production deployments. Feature branch deploys should target preview environments.
- **Skipping the health check.** A successful `wrangler deploy` means the code was accepted by
  Cloudflare, not that it functions correctly. Always verify with a real HTTP request.
- **Using `--no-bundle` in CI.** This skips Wrangler's bundling step, which may produce a
  different artifact than what was tested locally.
- **Storing `CLOUDFLARE_API_TOKEN` in `wrangler.toml`.** Config files are committed to the
  repository. Always inject secrets via environment variables from CI secrets storage.

---

## Gotchas

- `wrangler rollback` reverts to the most recent previous version by default. If two deploys
  happened before the health check ran, rollback goes to the second-most-recent, not the
  last-known-good. For stricter control, capture the version ID before deploy and pass it
  explicitly: `wrangler rollback <version-id>`.
- GitHub Actions `environment:` with `url:` sets the deployment URL visible in the PR and on the
  repository's Deployments page, but only if the job runs in a named environment.
- The `concurrency.cancel-in-progress: false` setting means a queued deploy will wait
  indefinitely if the preceding deploy hangs. Set a job-level `timeout-minutes` to avoid this.
- Cloudflare's deployment propagation is near-instant globally, but DNS TTL for custom domains
  can delay health check success by up to 60 seconds on the first deploy.

---

## Verification

```bash
# Manually trigger a deploy and watch the workflow
gh workflow run deploy.yml --ref main
gh run watch

# Confirm the deployed version matches the commit
curl -s https://my-worker-production.example.workers.dev/health | jq .version
git rev-parse --short HEAD

# List recent deployments
npx wrangler deployments list --env production

# Test rollback manually
npx wrangler rollback --env production --message "manual test rollback"
```

---

## Related

- `workers-monorepo-selective-deploy-changeset.md` — deploy only changed Workers
- `workers-bisect-regression-isolation.md` — find the commit that broke production
- `workers-worktree-parallel-wrangler-dev.md` — local parallel development before pushing

---

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/workers/wrangler/commands/#rollback
- https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- https://developers.cloudflare.com/workers/configuration/environments/
