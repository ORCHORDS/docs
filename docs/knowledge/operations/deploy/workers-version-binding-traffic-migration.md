# Migrating Traffic Using Workers Versions API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to gradually shift production traffic from one Worker version to a new one
(e.g. 0 % → 10 % → 50 % → 100 %) while monitoring error rates, rather than doing an
instant cutover with `wrangler deploy`.

## Context

- Cloudflare Workers Versions API (available on Workers Paid plan).
- `wrangler versions upload` creates an undeployed version artifact.
- `wrangler deployments create` creates a deployment that maps percentage splits to
  version IDs.
- Error-rate monitoring is done via the Cloudflare GraphQL Analytics API.

---

## Section 1 — Upload a new version without routing traffic

```bash
# Upload the new worker code as a version (does NOT route any traffic)
npx wrangler versions upload \
  --message "v2 – new caching layer" \
  --tag "v2.0.0"

# The command prints the new version ID — capture it:
VERSION_ID=$(npx wrangler versions upload \
  --message "v2 – new caching layer" \
  --tag "v2.0.0" 2>&1 \
  | grep -oP '(?<=Version ID: )[\w-]+')

echo "Uploaded version: $VERSION_ID"

# List all versions to find the current stable version ID
npx wrangler versions list
```

Example `versions list` output:

```
 Version ID                             Tag       Message                   Created
 ────────────────────────────────────── ───────── ──────────────────────── ──────────────────────
 3f8e1a2b-0001-4c3d-9abc-111111111111  v2.0.0   v2 – new caching layer   2026-08-24T10:00:00Z
 a1b2c3d4-0001-4c3d-9abc-000000000000  v1.9.3   previous stable          2026-08-23T08:00:00Z
```

---

## Section 2 — Progressive traffic split with deployments create

```bash
# Variables
STABLE_VERSION="a1b2c3d4-0001-4c3d-9abc-000000000000"
CANARY_VERSION="3f8e1a2b-0001-4c3d-9abc-111111111111"
WORKER_NAME="my-api-worker"

# Step 1: Route 10 % to new version
npx wrangler deployments create \
  --version-id "$CANARY_VERSION" --version-percentage 10 \
  --version-id "$STABLE_VERSION" --version-percentage 90 \
  --message "canary: 10 % to v2"

# Step 2: After observing metrics — bump to 50 %
npx wrangler deployments create \
  --version-id "$CANARY_VERSION" --version-percentage 50 \
  --version-id "$STABLE_VERSION" --version-percentage 50 \
  --message "canary: 50 % to v2"

# Step 3: Full cutover
npx wrangler deployments create \
  --version-id "$CANARY_VERSION" --version-percentage 100 \
  --message "full cutover to v2"
```

Typescript helper that automates the ramp:

```typescript
// scripts/traffic-ramp.ts
import { execSync } from 'node:child_process';

const RAMP_STEPS = [10, 30, 50, 100]; // percentages
const WAIT_SECONDS = 120; // observation window between steps
const ERROR_RATE_THRESHOLD = 0.5; // percent — abort if exceeded

const STABLE_VERSION = process.env.STABLE_VERSION!;
const CANARY_VERSION = process.env.CANARY_VERSION!;
const WORKER_NAME = process.env.WORKER_NAME!;
const CF_ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;

async function getErrorRate(windowMinutes = 5): Promise<number> {
  const query = `{
    viewer {
      accounts(filter: { accountTag: "${CF_ACCOUNT_ID}" }) {
        workersInvocationsAdaptive(
          limit: 1
          filter: {
            datetime_geq: "${new Date(Date.now() - windowMinutes * 60_000).toISOString()}"
            scriptName: "${WORKER_NAME}"
          }
          orderBy: [datetime_DESC]
        ) {
          sum { errors requests }
        }
      }
    }
  }`;

  const response = await fetch('https://api.cloudflare.com/client/v4/graphql', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query }),
  });

  const data = await response.json() as {
    data: { viewer: { accounts: [{ workersInvocationsAdaptive: [{ sum: { errors: number; requests: number } }] }] } }
  };

  const stats = data.data.viewer.accounts[0]?.workersInvocationsAdaptive?.[0]?.sum;
  if (!stats || stats.requests === 0) return 0;
  return (stats.errors / stats.requests) * 100;
}

function deploy(canaryPct: number): void {
  const stablePct = 100 - canaryPct;
  const args = canaryPct < 100
    ? `--version-id "${CANARY_VERSION}" --version-percentage ${canaryPct} --version-id "${STABLE_VERSION}" --version-percentage ${stablePct}`
    : `--version-id "${CANARY_VERSION}" --version-percentage 100`;

  execSync(`npx wrangler deployments create ${args} --message "canary ${canaryPct}%"`, {
    stdio: 'inherit',
    env: process.env as NodeJS.ProcessEnv,
  });
}

for (const step of RAMP_STEPS) {
  console.log(`\n--- Routing ${step}% to canary ---`);
  deploy(step);

  if (step < 100) {
    console.log(`Waiting ${WAIT_SECONDS}s to observe error rate...`);
    await new Promise(r => setTimeout(r, WAIT_SECONDS * 1_000));

    const errorRate = await getErrorRate();
    console.log(`Error rate: ${errorRate.toFixed(2)}%`);

    if (errorRate > ERROR_RATE_THRESHOLD) {
      console.error(`Error rate ${errorRate.toFixed(2)}% exceeds threshold ${ERROR_RATE_THRESHOLD}% — rolling back.`);
      deploy(0);
      execSync(`npx wrangler deployments create --version-id "${STABLE_VERSION}" --version-percentage 100 --message "rollback: error rate exceeded"`, {
        stdio: 'inherit',
      });
      process.exit(1);
    }
  }
}

console.log('\nTraffic migration complete.');
```

---

## Section 3 — Verify the active deployment

```bash
# Show current deployment split
npx wrangler deployments list

# Tail real-time logs for the canary version
npx wrangler tail --version-id "$CANARY_VERSION"

# Query error rate via GraphQL (curl shorthand)
curl -fsSL -X POST 'https://api.cloudflare.com/client/v4/graphql' \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{
    "query": "{ viewer { accounts(filter:{accountTag:\"'$CLOUDFLARE_ACCOUNT_ID'\"}) { workersInvocationsAdaptive(limit:1 filter:{scriptName:\"my-api-worker\",datetime_geq:\"2026-08-24T09:00:00Z\"}) { sum { errors requests } } } } }"
  }'
```

---

## Anti-patterns

- **Using `wrangler deploy` for canary** — `wrangler deploy` always routes 100 % to the
  new version; use `wrangler versions upload` + `wrangler deployments create` instead.
- **Skipping the error-rate check** — traffic splits without observability are the same
  risk as a full cutover.
- **Setting the observation window too short** — error rates can be noisy; a 2–5 minute
  window smooths out transient spikes.
- **Not pinning the stable version ID** — if you omit the stable version from
  `deployments create`, Cloudflare treats it as 0 %.

## Gotchas

- Workers Versions API requires **Workers Paid plan** — it is not available on the free tier.
- `--version-id` flags are order-sensitive in some wrangler versions; list canary first
  and stable second for predictability.
- The GraphQL Analytics API has a short ingestion delay (~1–2 min); do not poll
  immediately after a deployment step.
- `wrangler versions upload` does NOT execute the `[build]` step in `wrangler.toml`;
  run your build beforehand.

## Related

- `workers-deployment-slack-webhook-notification.md`
- `workers-deployment-gates-manual-approval.md`
- `workers-pipeline-worker-chained-deploy.md`

## Sources

- Workers Versions: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Cloudflare GraphQL Analytics: https://developers.cloudflare.com/analytics/graphql-api/
- Wrangler deployments command: https://developers.cloudflare.com/workers/wrangler/commands/#deployments
